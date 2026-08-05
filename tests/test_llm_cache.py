"""Unit tests for tooldex/scanner/llm_cache.py."""
from types import SimpleNamespace

from tooldex.scanner import llm_cache


class TestToolHash:
    def test_same_inputs_same_hash(self):
        h1 = llm_cache.tool_hash("sync", "Sync notes", {"type": "object"})
        h2 = llm_cache.tool_hash("sync", "Sync notes", {"type": "object"})
        assert h1 == h2

    def test_different_description_different_hash(self):
        h1 = llm_cache.tool_hash("sync", "Sync notes", {})
        h2 = llm_cache.tool_hash("sync", "Sync notes v2", {})
        assert h1 != h2

    def test_different_name_different_hash(self):
        h1 = llm_cache.tool_hash("sync", "desc", {})
        h2 = llm_cache.tool_hash("sync2", "desc", {})
        assert h1 != h2

    def test_different_schema_different_hash(self):
        h1 = llm_cache.tool_hash("t", "d", {"type": "object"})
        h2 = llm_cache.tool_hash("t", "d", {"type": "string"})
        assert h1 != h2

    def test_none_description_and_schema_do_not_crash(self):
        h = llm_cache.tool_hash("t", None, None)
        assert isinstance(h, str) and h


class TestGetPutCached:
    def test_round_trip(self):
        h = llm_cache.tool_hash("sync", "desc", {})
        llm_cache.put_cached("srv:a", "sync", h, [{"severity": "HIGH"}], is_safe=False)
        result = llm_cache.get_cached("srv:a", "sync", h)
        assert result == {"findings": [{"severity": "HIGH"}], "is_safe": False}

    def test_miss_when_never_cached(self):
        h = llm_cache.tool_hash("sync", "desc", {})
        assert llm_cache.get_cached("srv:a", "sync", h) is None

    def test_miss_on_hash_mismatch(self):
        h1 = llm_cache.tool_hash("sync", "desc", {})
        h2 = llm_cache.tool_hash("sync", "desc v2", {})
        llm_cache.put_cached("srv:a", "sync", h1, [], is_safe=True)
        assert llm_cache.get_cached("srv:a", "sync", h2) is None

    def test_distinct_servers_do_not_collide(self):
        h = llm_cache.tool_hash("sync", "desc", {})
        llm_cache.put_cached("srv:a", "sync", h, [{"severity": "HIGH"}], is_safe=False)
        llm_cache.put_cached("srv:b", "sync", h, [], is_safe=True)
        assert llm_cache.get_cached("srv:a", "sync", h)["is_safe"] is False
        assert llm_cache.get_cached("srv:b", "sync", h)["is_safe"] is True

    def test_overwrite_updates_entry(self):
        h = llm_cache.tool_hash("sync", "desc", {})
        llm_cache.put_cached("srv:a", "sync", h, [], is_safe=True)
        llm_cache.put_cached("srv:a", "sync", h, [{"severity": "LOW"}], is_safe=False)
        assert llm_cache.get_cached("srv:a", "sync", h) == {"findings": [{"severity": "LOW"}], "is_safe": False}


class TestInvalidateServer:
    def test_removes_only_that_servers_entries(self):
        h = llm_cache.tool_hash("t", "d", {})
        llm_cache.put_cached("srv:a", "t", h, [], is_safe=True)
        llm_cache.put_cached("srv:b", "t", h, [], is_safe=True)

        removed = llm_cache.invalidate_server("srv:a")

        assert removed == 1
        assert llm_cache.get_cached("srv:a", "t", h) is None
        assert llm_cache.get_cached("srv:b", "t", h) is not None

    def test_removes_multiple_tools_for_same_server(self):
        h = llm_cache.tool_hash("t", "d", {})
        llm_cache.put_cached("srv:a", "tool1", h, [], is_safe=True)
        llm_cache.put_cached("srv:a", "tool2", h, [], is_safe=True)

        removed = llm_cache.invalidate_server("srv:a")
        assert removed == 2

    def test_no_entries_returns_zero(self):
        assert llm_cache.invalidate_server("srv:nonexistent") == 0

    def test_prefix_collision_is_not_a_false_match(self):
        # "srv:a" must not accidentally invalidate "srv:ab"
        h = llm_cache.tool_hash("t", "d", {})
        llm_cache.put_cached("srv:a", "t", h, [], is_safe=True)
        llm_cache.put_cached("srv:ab", "t", h, [], is_safe=True)

        llm_cache.invalidate_server("srv:a")

        assert llm_cache.get_cached("srv:ab", "t", h) is not None


class TestHasEntriesFor:
    def test_true_after_put(self):
        h = llm_cache.tool_hash("t", "d", {})
        llm_cache.put_cached("srv:a", "t", h, [], is_safe=True)
        assert llm_cache.has_entries_for("srv:a") is True

    def test_false_when_never_cached(self):
        assert llm_cache.has_entries_for("srv:never") is False

    def test_false_after_invalidate(self):
        h = llm_cache.tool_hash("t", "d", {})
        llm_cache.put_cached("srv:a", "t", h, [], is_safe=True)
        llm_cache.invalidate_server("srv:a")
        assert llm_cache.has_entries_for("srv:a") is False

    def test_ignores_hash_validity(self):
        # has_entries_for is about existence, not whether the cached hash
        # still matches the tool's current identity
        h = llm_cache.tool_hash("t", "old description", {})
        llm_cache.put_cached("srv:a", "t", h, [], is_safe=True)
        assert llm_cache.has_entries_for("srv:a") is True


class TestGetAllMatching:
    def test_returns_matching_tools_only(self):
        tool_a = SimpleNamespace(name="a", description="desc a", input_schema={})
        tool_b = SimpleNamespace(name="b", description="desc b", input_schema={})
        h_a = llm_cache.tool_hash("a", "desc a", {})
        llm_cache.put_cached("srv:x", "a", h_a, [{"severity": "HIGH"}], is_safe=False)
        # "b" was never scanned/cached

        matched = llm_cache.get_all_matching("srv:x", [tool_a, tool_b])

        assert set(matched.keys()) == {"a"}
        assert matched["a"]["is_safe"] is False
        assert matched["a"]["findings"] == [{"severity": "HIGH"}]
        assert "ts" in matched["a"]

    def test_stale_hash_excluded(self):
        tool = SimpleNamespace(name="a", description="new description", input_schema={})
        old_hash = llm_cache.tool_hash("a", "old description", {})
        llm_cache.put_cached("srv:x", "a", old_hash, [], is_safe=True)

        matched = llm_cache.get_all_matching("srv:x", [tool])

        assert matched == {}

    def test_empty_tools_list_returns_empty(self):
        assert llm_cache.get_all_matching("srv:x", []) == {}
