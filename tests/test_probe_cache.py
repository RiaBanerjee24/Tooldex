"""Unit tests for tooldex/core/discovery/probe_cache.py."""
import pytest

from tooldex.core.discovery import probe_cache
from tooldex.core.discovery.results import DiscoveredTool, ToolDiscoveryResult, ToolDiscoveryStatus
from tooldex.core.models.server import MCPServer


@pytest.fixture(autouse=True)
def isolated_probe_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(probe_cache, "_CACHE_PATH", tmp_path / "probe_cache.json")


def _server(**overrides):
    defaults = dict(id="a:srv", name="srv", command="npx", args=["-y", "pkg"], transport="stdio")
    defaults.update(overrides)
    return MCPServer(**defaults)


def _result(server_id="a:srv"):
    return ToolDiscoveryResult(
        server_id=server_id,
        status=ToolDiscoveryStatus.FOUND,
        tools=[DiscoveredTool(name="t1", server_id=server_id, description="d", input_schema={})],
        duration_ms=123,
    )


class TestServerKey:
    def test_deterministic_for_same_config(self):
        assert probe_cache._server_key(_server()) == probe_cache._server_key(_server())

    def test_differs_by_command(self):
        assert probe_cache._server_key(_server(command="npx")) != probe_cache._server_key(_server(command="uvx"))

    def test_differs_by_args(self):
        assert probe_cache._server_key(_server(args=["a"])) != probe_cache._server_key(_server(args=["b"]))

    def test_differs_by_env_keys_not_values(self):
        s1 = _server(env={"API_KEY": "secret1"})
        s2 = _server(env={"API_KEY": "secret2"})
        # env VALUES shouldn't matter (they can change without invalidating cache identity)
        assert probe_cache._server_key(s1) == probe_cache._server_key(s2)

    def test_differs_by_env_key_names(self):
        s1 = _server(env={"API_KEY": "x"})
        s2 = _server(env={"OTHER_KEY": "x"})
        assert probe_cache._server_key(s1) != probe_cache._server_key(s2)


class TestGetPutCached:
    def test_round_trip(self):
        server = _server()
        probe_cache.put_cached(server, _result())
        cached = probe_cache.get_cached(server)
        assert cached is not None
        assert cached.server_id == "a:srv"
        assert cached.status == ToolDiscoveryStatus.FOUND
        assert len(cached.tools) == 1
        assert cached.tools[0].name == "t1"
        assert cached.duration_ms == 123

    def test_miss_when_never_cached(self):
        assert probe_cache.get_cached(_server()) is None

    def test_miss_when_stale(self, monkeypatch):
        server = _server()
        probe_cache.put_cached(server, _result())
        # ttl=0 means anything not probed in the same instant is stale
        assert probe_cache.get_cached(server, ttl=0) is None

    def test_hit_within_ttl(self):
        server = _server()
        probe_cache.put_cached(server, _result())
        assert probe_cache.get_cached(server, ttl=300) is not None

    def test_different_servers_do_not_collide(self):
        s1, s2 = _server(id="a:one", command="npx"), _server(id="a:two", command="uvx")
        probe_cache.put_cached(s1, _result("a:one"))
        assert probe_cache.get_cached(s2) is None

    def test_malformed_entry_returns_none_not_raise(self):
        server = _server()
        key = probe_cache._server_key(server)
        probe_cache._save({key: {"garbage": True}})
        assert probe_cache.get_cached(server) is None


class TestInvalidate:
    def test_removes_cached_entry(self):
        server = _server()
        probe_cache.put_cached(server, _result())
        probe_cache.invalidate(server)
        assert probe_cache.get_cached(server) is None

    def test_noop_when_nothing_cached(self):
        probe_cache.invalidate(_server())  # must not raise
