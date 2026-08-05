"""Unit tests for tooldex/core/discovery/mcp_client.py.

Pure helpers get direct unit tests. The async probe functions are tested by
mocking asyncio.create_subprocess_exec / the mcp SDK boundary — never a real
subprocess or network connection.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tooldex.core.discovery import mcp_client
from tooldex.core.discovery.results import ToolDiscoveryStatus
from tooldex.core.models.server import MCPServer


def _server(**overrides):
    defaults = dict(id="a:srv", name="srv", transport="stdio", command="npx", args=[])
    defaults.update(overrides)
    return MCPServer(**defaults)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestFallbackCmd:
    def test_cursor_client_has_a_fallback(self):
        assert mcp_client._fallback_cmd("cursor_user") == ["cursor-agent", "mcp", "list-tools"]

    def test_unregistered_client_returns_none(self):
        assert mcp_client._fallback_cmd("claude_code_user") is None

    def test_none_client_returns_none(self):
        assert mcp_client._fallback_cmd(None) is None

    def test_empty_string_returns_none(self):
        assert mcp_client._fallback_cmd("") is None


class TestRootCause:
    def test_plain_exception_returns_itself(self):
        exc = ValueError("boom")
        assert mcp_client._root_cause(exc) is exc

    def test_unwraps_exception_group_like_object(self):
        inner = RuntimeError("inner")
        outer = SimpleNamespace(exceptions=[inner])
        assert mcp_client._root_cause(outer) is inner

    def test_unwraps_nested_groups_recursively(self):
        innermost = ValueError("deepest")
        mid = SimpleNamespace(exceptions=[innermost])
        outer = SimpleNamespace(exceptions=[mid])
        assert mcp_client._root_cause(outer) is innermost

    def test_real_exception_group(self):
        innermost = ValueError("real")
        eg = ExceptionGroup("group", [innermost])
        assert mcp_client._root_cause(eg) is innermost


class TestToDict:
    def test_none_stays_none(self):
        assert mcp_client._to_dict(None) is None

    def test_dict_passed_through(self):
        d = {"type": "object"}
        assert mcp_client._to_dict(d) is d

    def test_object_with_model_dump_is_converted(self):
        obj = SimpleNamespace(model_dump=lambda: {"type": "object"})
        assert mcp_client._to_dict(obj) == {"type": "object"}

    def test_object_without_model_dump_returns_none(self):
        assert mcp_client._to_dict(object()) is None


class TestParseAgentOutput:
    def test_parses_tools_with_and_without_params(self):
        output = "Tools for browserbase (3):\n- act (action)\n- end ()\n- navigate\n"
        tools = mcp_client._parse_agent_output(output, "a:srv")
        assert [t.name for t in tools] == ["act", "end", "navigate"]
        assert tools[0].description == "action"
        assert tools[1].description is None  # empty parens -> no description
        assert tools[2].description is None  # no parens at all

    def test_ignores_non_bullet_lines(self):
        output = "Tools for x (1):\nsome preamble\n- real_tool\ntrailing junk\n"
        tools = mcp_client._parse_agent_output(output, "a:srv")
        assert [t.name for t in tools] == ["real_tool"]

    def test_empty_output_returns_empty_list(self):
        assert mcp_client._parse_agent_output("", "a:srv") == []

    def test_tools_tagged_with_server_id(self):
        tools = mcp_client._parse_agent_output("- t1\n", "a:srv")
        assert tools[0].server_id == "a:srv"


# ---------------------------------------------------------------------------
# _probe_with_timeout
# ---------------------------------------------------------------------------

class TestProbeWithTimeout:
    @pytest.mark.asyncio
    async def test_success_sets_duration_ms(self):
        async def ok(server):
            return SimpleNamespace(server_id=server.id, status=ToolDiscoveryStatus.FOUND, tools=[], ok=True, duration_ms=None)

        result = await mcp_client._probe_with_timeout(ok, _server(), timeout=5.0)
        assert result.status == ToolDiscoveryStatus.FOUND
        assert result.duration_ms is not None

    @pytest.mark.asyncio
    async def test_timeout_error_becomes_timeout_status(self):
        async def slow(server):
            await asyncio.sleep(10)

        result = await mcp_client._probe_with_timeout(slow, _server(), timeout=0.01)
        assert result.status == ToolDiscoveryStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_file_not_found_includes_runtime_hint(self):
        async def missing_binary(server):
            raise FileNotFoundError()

        result = await mcp_client._probe_with_timeout(missing_binary, _server(command="npx"), timeout=5.0)
        assert result.status == ToolDiscoveryStatus.CONNECTION_FAILED
        assert "npx" in result.error
        assert "Node.js" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found_unknown_command_no_hint_crash(self):
        async def missing_binary(server):
            raise FileNotFoundError()

        result = await mcp_client._probe_with_timeout(missing_binary, _server(command="some-obscure-tool"), timeout=5.0)
        assert result.status == ToolDiscoveryStatus.CONNECTION_FAILED
        assert "some-obscure-tool" in result.error

    @pytest.mark.asyncio
    async def test_generic_exception_becomes_protocol_error_with_root_cause(self):
        async def broken(server):
            raise ValueError("weird handshake failure")

        result = await mcp_client._probe_with_timeout(broken, _server(), timeout=5.0)
        assert result.status == ToolDiscoveryStatus.PROTOCOL_ERROR
        assert "ValueError" in result.error
        assert "weird handshake failure" in result.error


# ---------------------------------------------------------------------------
# _probe_stdio / _probe_http / _probe_sse — input validation branches
# ---------------------------------------------------------------------------

class TestProbeStdioValidation:
    @pytest.mark.asyncio
    async def test_missing_command_returns_missing_command_status(self):
        result = await mcp_client._probe_stdio(_server(command=None))
        assert result.status == ToolDiscoveryStatus.MISSING_COMMAND


class TestProbeHttpValidation:
    @pytest.mark.asyncio
    async def test_missing_url_returns_connection_failed(self):
        result = await mcp_client._probe_http(_server(transport="http", command=None, url=None))
        assert result.status == ToolDiscoveryStatus.CONNECTION_FAILED
        assert "url" in result.error


class TestProbeSseValidation:
    @pytest.mark.asyncio
    async def test_missing_url_returns_connection_failed(self):
        result = await mcp_client._probe_sse(_server(transport="sse", command=None, url=None))
        assert result.status == ToolDiscoveryStatus.CONNECTION_FAILED
        assert "url" in result.error


# ---------------------------------------------------------------------------
# _probe_via_agent
# ---------------------------------------------------------------------------

class TestProbeViaAgent:
    @pytest.mark.asyncio
    async def test_no_fallback_registered_returns_unsupported_transport(self):
        server = _server(transport="http", command=None, url="https://x", client="claude_code_user")
        result = await mcp_client._probe_via_agent(server)
        assert result.status == ToolDiscoveryStatus.UNSUPPORTED_TRANSPORT

    @pytest.mark.asyncio
    async def test_binary_not_found(self):
        server = _server(transport="http", command=None, url="https://x", client="cursor_user")
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
            result = await mcp_client._probe_via_agent(server)
        assert result.status == ToolDiscoveryStatus.CONNECTION_FAILED
        assert "cursor-agent" in result.error

    @pytest.mark.asyncio
    async def test_timeout(self):
        server = _server(transport="http", command=None, url="https://x", client="cursor_user")
        fake_proc = AsyncMock()
        fake_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)), \
             patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = await mcp_client._probe_via_agent(server)
        assert result.status == ToolDiscoveryStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_success_with_tools_found(self):
        server = _server(transport="http", command=None, url="https://x", client="cursor_user", name="browserbase")
        fake_proc = AsyncMock()
        output = b"Tools for browserbase (1):\n- act (action)\n"
        fake_proc.communicate = AsyncMock(return_value=(output, b""))
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)):
            result = await mcp_client._probe_via_agent(server)
        assert result.status == ToolDiscoveryStatus.FOUND
        assert len(result.tools) == 1

    @pytest.mark.asyncio
    async def test_no_tools_in_output_returns_empty(self):
        server = _server(transport="http", command=None, url="https://x", client="cursor_user")
        fake_proc = AsyncMock()
        fake_proc.communicate = AsyncMock(return_value=(b"no tools here", b""))
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)):
            result = await mcp_client._probe_via_agent(server)
        assert result.status == ToolDiscoveryStatus.EMPTY


# ---------------------------------------------------------------------------
# probe_server routing
# ---------------------------------------------------------------------------

class TestProbeServerRouting:
    @pytest.mark.asyncio
    async def test_stdio_routes_to_probe_stdio(self):
        server = _server(transport="stdio")
        with patch.object(mcp_client, "_probe_stdio", new=AsyncMock(
            return_value=SimpleNamespace(server_id="a:srv", status=ToolDiscoveryStatus.FOUND, ok=True, tools=[], duration_ms=None)
        )) as mock_probe:
            result = await mcp_client.probe_server(server)
        mock_probe.assert_called_once()
        assert result.status == ToolDiscoveryStatus.FOUND

    @pytest.mark.asyncio
    async def test_unsupported_transport(self):
        server = _server(transport="carrier-pigeon")
        result = await mcp_client.probe_server(server)
        assert result.status == ToolDiscoveryStatus.UNSUPPORTED_TRANSPORT

    @pytest.mark.asyncio
    async def test_http_failure_falls_back_to_agent_when_registered(self):
        server = _server(transport="http", command=None, url="https://x", client="cursor_user")
        failed = SimpleNamespace(server_id="a:srv", status=ToolDiscoveryStatus.CONNECTION_FAILED, ok=False, tools=[], error="failed", duration_ms=1)
        succeeded = SimpleNamespace(server_id="a:srv", status=ToolDiscoveryStatus.FOUND, ok=True, tools=["t"], error=None, duration_ms=1)
        with patch.object(mcp_client, "_probe_http", new=AsyncMock(return_value=failed)), \
             patch.object(mcp_client, "_probe_via_agent", new=AsyncMock(return_value=succeeded)) as mock_agent:
            result = await mcp_client.probe_server(server)
        mock_agent.assert_called_once()
        assert result.status == ToolDiscoveryStatus.FOUND

    @pytest.mark.asyncio
    async def test_http_failure_no_fallback_registered_returns_original_failure(self):
        server = _server(transport="http", command=None, url="https://x", client="claude_code_user")
        failed = SimpleNamespace(server_id="a:srv", status=ToolDiscoveryStatus.CONNECTION_FAILED, ok=False, tools=[], error="failed", duration_ms=1)
        with patch.object(mcp_client, "_probe_http", new=AsyncMock(return_value=failed)):
            result = await mcp_client.probe_server(server)
        assert result.status == ToolDiscoveryStatus.CONNECTION_FAILED

    @pytest.mark.asyncio
    async def test_http_success_does_not_try_fallback(self):
        server = _server(transport="http", command=None, url="https://x", client="cursor_user")
        ok_result = SimpleNamespace(server_id="a:srv", status=ToolDiscoveryStatus.FOUND, ok=True, tools=["t"], error=None, duration_ms=1)
        with patch.object(mcp_client, "_probe_http", new=AsyncMock(return_value=ok_result)), \
             patch.object(mcp_client, "_probe_via_agent", new=AsyncMock()) as mock_agent:
            await mcp_client.probe_server(server)
        mock_agent.assert_not_called()


# ---------------------------------------------------------------------------
# _run_session
# ---------------------------------------------------------------------------

class TestRunSession:
    @pytest.mark.asyncio
    async def test_converts_mcp_tools_to_discovered_tools(self):
        fake_tool = SimpleNamespace(name="t1", description="desc", inputSchema={"type": "object"})
        fake_session = AsyncMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.initialize = AsyncMock()
        fake_session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=[fake_tool]))

        with patch("mcp.ClientSession", return_value=fake_session):
            result = await mcp_client._run_session(None, None, "a:srv")

        assert result.status == ToolDiscoveryStatus.FOUND
        assert len(result.tools) == 1
        assert result.tools[0].name == "t1"
        assert result.tools[0].input_schema == {"type": "object"}

    @pytest.mark.asyncio
    async def test_no_tools_returns_empty_status(self):
        fake_session = AsyncMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_session)
        fake_session.__aexit__ = AsyncMock(return_value=False)
        fake_session.initialize = AsyncMock()
        fake_session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=[]))

        with patch("mcp.ClientSession", return_value=fake_session):
            result = await mcp_client._run_session(None, None, "a:srv")

        assert result.status == ToolDiscoveryStatus.EMPTY


# ---------------------------------------------------------------------------
# probe_all
# ---------------------------------------------------------------------------

class TestProbeAll:
    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        assert await mcp_client.probe_all([]) == []

    @pytest.mark.asyncio
    async def test_preserves_input_order(self):
        servers = [_server(id=f"a:s{i}", name=f"s{i}") for i in range(5)]

        async def fake_probe(server, timeout=10.0):
            # deliberately vary "completion order" via sleep
            await asyncio.sleep(0.001 * (5 - int(server.id[-1])))
            return SimpleNamespace(server_id=server.id, status=ToolDiscoveryStatus.FOUND, ok=True, tools=[], duration_ms=1)

        with patch.object(mcp_client, "probe_server", new=fake_probe):
            results = await mcp_client.probe_all(servers)

        assert [r.server_id for r in results] == [s.id for s in servers]

    @pytest.mark.asyncio
    async def test_one_failure_does_not_stop_others(self):
        good = _server(id="a:good", name="good")
        bad = _server(id="a:bad", name="bad")

        async def fake_probe(server, timeout=10.0):
            if server.id == "a:bad":
                return SimpleNamespace(server_id="a:bad", status=ToolDiscoveryStatus.PROTOCOL_ERROR, ok=False, tools=[], duration_ms=1)
            return SimpleNamespace(server_id="a:good", status=ToolDiscoveryStatus.FOUND, ok=True, tools=[], duration_ms=1)

        with patch.object(mcp_client, "probe_server", new=fake_probe):
            results = await mcp_client.probe_all([good, bad])

        statuses = {r.server_id: r.status for r in results}
        assert statuses["a:good"] == ToolDiscoveryStatus.FOUND
        assert statuses["a:bad"] == ToolDiscoveryStatus.PROTOCOL_ERROR

    @pytest.mark.asyncio
    async def test_on_result_callback_fires_per_server(self):
        servers = [_server(id="a:x", name="x")]
        seen = []

        async def fake_probe(server, timeout=10.0):
            return SimpleNamespace(server_id=server.id, status=ToolDiscoveryStatus.FOUND, ok=True, tools=[], duration_ms=1)

        async def on_result(result):
            seen.append(result.server_id)

        with patch.object(mcp_client, "probe_server", new=fake_probe):
            await mcp_client.probe_all(servers, on_result=on_result)

        assert seen == ["a:x"]
