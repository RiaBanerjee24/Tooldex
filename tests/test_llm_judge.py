"""Unit tests for tooldex/scanner/llm_judge.py."""
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tooldex.scanner import llm_cache
from tooldex.scanner.llm_judge import (
    _check_llm_auth,
    _status_error_from_records,
    run_llm_judge_scan,
)


def _make_record(message: str, exc: Exception | None = None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="mcpscanner.core.analyzers.base.LLMAnalyzer",
        level=logging.ERROR, pathname="", lineno=0,
        msg=message, args=(), exc_info=None,
    )
    if exc is not None:
        try:
            raise exc
        except Exception:
            import sys
            record.exc_info = sys.exc_info()
    return record


class TestStatusErrorFromRecords:
    def test_extracts_status_from_real_exception_object(self):
        exc = Exception("Your API key has been invalidated.")
        exc.status_code = 401
        record = _make_record("LLM analysis failed for sync: ...", exc=exc)
        result = _status_error_from_records([record])
        assert result is not None
        assert "rejected the API key" in result

    def test_falls_back_to_message_regex_when_no_exc_info(self):
        record = _make_record("LLM call failed with status 429 rate limited")
        result = _status_error_from_records([record])
        assert result is not None
        assert "rate limit" in result.lower()

    def test_none_when_exception_has_no_status_code_and_message_has_no_code(self):
        exc = Exception("some transient network error")
        record = _make_record("LLM analysis failed: some transient network error", exc=exc)
        assert _status_error_from_records([record]) is None

    def test_none_for_empty_records(self):
        assert _status_error_from_records([]) is None

    def test_checks_later_records_when_earlier_ones_have_no_status(self):
        r1 = _make_record("some unrelated warning")
        exc = Exception("denied")
        exc.status_code = 403
        r2 = _make_record("LLM analysis failed for tool: denied", exc=exc)
        result = _status_error_from_records([r1, r2])
        assert result is not None
        assert "denied access" in result

    def test_unmapped_status_code_gets_generic_message(self):
        exc = Exception("teapot")
        exc.status_code = 418
        record = _make_record("...", exc=exc)
        # 418 isn't in _LLM_STATUS_MESSAGES, but any real status code from the
        # exception object still produces a message rather than being dropped
        assert _status_error_from_records([record]) == "LLM call failed with status 418"

    def test_known_but_unmapped_regex_code_gets_generic_message(self):
        record = _make_record("upstream returned 503 service unavailable")
        result = _status_error_from_records([record])
        assert result == "LLM call failed with status 503"


class TestCheckLlmAuth:
    def _config(self):
        return SimpleNamespace(
            llm_model="gpt-4o", llm_temperature=1.0, llm_timeout=30,
            llm_provider_api_key="sk-test", llm_base_url=None, llm_api_version=None,
        )

    @pytest.mark.asyncio
    async def test_passes_silently_on_success(self):
        with patch("litellm.acompletion", new=AsyncMock(return_value=None)):
            await _check_llm_auth(self._config())  # must not raise

    @pytest.mark.asyncio
    async def test_raises_friendly_message_for_401(self):
        exc = Exception("invalid key")
        exc.status_code = 401
        with patch("litellm.acompletion", new=AsyncMock(side_effect=exc)):
            with pytest.raises(ValueError, match="rejected the API key"):
                await _check_llm_auth(self._config())

    @pytest.mark.asyncio
    async def test_raises_friendly_message_for_429(self):
        exc = Exception("slow down")
        exc.status_code = 429
        with patch("litellm.acompletion", new=AsyncMock(side_effect=exc)):
            with pytest.raises(ValueError, match="rate limit"):
                await _check_llm_auth(self._config())

    @pytest.mark.asyncio
    async def test_unknown_status_falls_back_to_raw_message(self):
        exc = Exception("weird provider error")
        exc.status_code = 599
        with patch("litellm.acompletion", new=AsyncMock(side_effect=exc)):
            with pytest.raises(ValueError, match="weird provider error"):
                await _check_llm_auth(self._config())


def _server(tools):
    return SimpleNamespace(
        id="test:srv", name="srv", transport="stdio",
        command="npx", args=[], env={}, url=None,
        discovered_tools=tools,
    )


def _tool(name, description="desc"):
    return SimpleNamespace(name=name, description=description, input_schema={})


class TestRunLlmJudgeScan:
    @pytest.mark.asyncio
    async def test_raises_when_no_api_key_configured(self):
        with patch("tooldex.scanner.llm_judge.build_config") as mock_cfg:
            mock_cfg.return_value = SimpleNamespace(llm_provider_api_key=None)
            with pytest.raises(ValueError, match="not configured"):
                await run_llm_judge_scan(_server([_tool("a")]))

    @pytest.mark.asyncio
    async def test_empty_tool_list_returns_empty_without_scanning(self):
        with patch("tooldex.scanner.llm_judge.build_config") as mock_cfg, \
             patch("tooldex.scanner.llm_judge.Scanner") as MockScanner, \
             patch("tooldex.scanner.llm_judge._check_llm_auth", new=AsyncMock()) as mock_auth:
            mock_cfg.return_value = SimpleNamespace(
                llm_provider_api_key="sk-test", llm_rate_limit_delay=2.0,
            )
            result = await run_llm_judge_scan(_server([]))
            assert result == []
            mock_auth.assert_not_called()
            MockScanner.return_value.scan_stdio_server_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_cache_hits_skips_auth_check_and_scanner_call(self):
        tool = _tool("sync")
        h = llm_cache.tool_hash("sync", "desc", {})
        llm_cache.put_cached("test:srv", "sync", h, [], is_safe=True)

        with patch("tooldex.scanner.llm_judge.build_config") as mock_cfg, \
             patch("tooldex.scanner.llm_judge.Scanner") as MockScanner, \
             patch("tooldex.scanner.llm_judge._check_llm_auth", new=AsyncMock()) as mock_auth:
            mock_cfg.return_value = SimpleNamespace(
                llm_provider_api_key="sk-test", llm_rate_limit_delay=0.01,
            )
            hits = []
            result = await run_llm_judge_scan(
                _server([tool]), on_cache_hit=hits.append, force=False,
            )
            assert len(result) == 1
            assert hits == ["sync"]
            mock_auth.assert_not_called()
            MockScanner.return_value.scan_stdio_server_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_true_ignores_cache_and_calls_scanner(self):
        tool = _tool("sync")
        h = llm_cache.tool_hash("sync", "desc", {})
        llm_cache.put_cached("test:srv", "sync", h, [], is_safe=True)

        scan_mock = AsyncMock(return_value=SimpleNamespace(tool_name="sync", is_safe=True, findings=[]))
        with patch("tooldex.scanner.llm_judge.build_config") as mock_cfg, \
             patch("tooldex.scanner.llm_judge.Scanner") as MockScanner, \
             patch("tooldex.scanner.llm_judge._check_llm_auth", new=AsyncMock()) as mock_auth:
            mock_cfg.return_value = SimpleNamespace(
                llm_provider_api_key="sk-test", llm_rate_limit_delay=0.01,
            )
            MockScanner.return_value.scan_stdio_server_tool = scan_mock

            hits = []
            await run_llm_judge_scan(_server([tool]), on_cache_hit=hits.append, force=True)

            mock_auth.assert_called_once()
            scan_mock.assert_called_once()
            assert hits == []

    @pytest.mark.asyncio
    async def test_progress_callback_fires_per_tool(self):
        tools = [_tool("a"), _tool("b")]
        scan_mock = AsyncMock(side_effect=lambda *a, **k: SimpleNamespace(
            tool_name="x", is_safe=True, findings=[],
        ))
        with patch("tooldex.scanner.llm_judge.build_config") as mock_cfg, \
             patch("tooldex.scanner.llm_judge.Scanner") as MockScanner, \
             patch("tooldex.scanner.llm_judge._check_llm_auth", new=AsyncMock()):
            mock_cfg.return_value = SimpleNamespace(
                llm_provider_api_key="sk-test", llm_rate_limit_delay=0.01,
            )
            MockScanner.return_value.scan_stdio_server_tool = scan_mock

            progress = []
            await run_llm_judge_scan(_server(tools), on_progress=lambda s, t: progress.append((s, t)), force=True)

            assert progress == [(1, 2), (2, 2)]

    @pytest.mark.asyncio
    async def test_cancel_event_already_set_stops_immediately(self):
        tools = [_tool("a"), _tool("b")]
        scan_mock = AsyncMock()
        with patch("tooldex.scanner.llm_judge.build_config") as mock_cfg, \
             patch("tooldex.scanner.llm_judge.Scanner") as MockScanner, \
             patch("tooldex.scanner.llm_judge._check_llm_auth", new=AsyncMock()):
            mock_cfg.return_value = SimpleNamespace(
                llm_provider_api_key="sk-test", llm_rate_limit_delay=0.01,
            )
            MockScanner.return_value.scan_stdio_server_tool = scan_mock

            cancel_event = asyncio.Event()
            cancel_event.set()
            result = await run_llm_judge_scan(_server(tools), cancel_event=cancel_event, force=True)

            assert result == []
            scan_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_mid_scan_key_revocation_stops_scan_and_does_not_report_false_clean(self):
        """Regression test: mcpscanner's LLMAnalyzer swallows LLM call
        failures internally and logs them via its own logger
        ("mcpscanner.core.analyzers.base.LLMAnalyzer"). A capture handler
        listening on the wrong logger would never see this, and every tool
        after the key died would silently come back "safe". This reproduces
        exactly that shape: tool 1 succeeds, tool 2's key has been revoked."""
        tools = [_tool("sync", "Sync"), _tool("get_due_cards", "Get due cards"), _tool("get_cards", "Get cards")]

        async def fake_scan(stdio_cfg, tool_name, analyzers=None, errlog=None):
            logger = logging.getLogger("mcpscanner.core.analyzers.base.LLMAnalyzer")
            if tool_name == "sync":
                return SimpleNamespace(tool_name=tool_name, is_safe=True, findings=[])
            try:
                exc = Exception("AuthenticationError: OpenAIException - Your API key has been invalidated.")
                exc.status_code = 401
                raise exc
            except Exception as e:
                logger.error(f"LLM analysis failed for {tool_name}: {str(e)}")
                logger.error(f"Full traceback for {tool_name}:", exc_info=True)
            return SimpleNamespace(tool_name=tool_name, is_safe=True, findings=[])  # swallowed -> looks "safe"

        with patch("tooldex.scanner.llm_judge.build_config") as mock_cfg, \
             patch("tooldex.scanner.llm_judge.Scanner") as MockScanner, \
             patch("tooldex.scanner.llm_judge._check_llm_auth", new=AsyncMock()):
            mock_cfg.return_value = SimpleNamespace(
                llm_provider_api_key="sk-fake-key-that-gets-revoked-midway",
                llm_rate_limit_delay=0.01,
            )
            MockScanner.return_value.scan_stdio_server_tool = fake_scan

            server = _server(tools)
            with pytest.raises(ValueError, match="rejected the API key"):
                await run_llm_judge_scan(server, force=True)

            # tool 1 (scanned before the key died) is cached; the tool that
            # hit the dead key is not cached as a false "clean"
            assert llm_cache.get_cached(
                "test:srv", "sync", llm_cache.tool_hash("sync", "Sync", {})
            ) is not None
            assert llm_cache.get_cached(
                "test:srv", "get_due_cards", llm_cache.tool_hash("get_due_cards", "Get due cards", {})
            ) is None
