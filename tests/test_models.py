"""Unit tests for tooldex/core/models/server.py and manifest.py."""
import pytest
from pydantic import ValidationError

from tooldex.core.models.manifest import TooldexManifest, TooldexMetadata
from tooldex.core.models.server import DiscoveredToolLite, MCPServer


class TestMCPServer:
    def test_requires_name(self):
        with pytest.raises(ValidationError):
            MCPServer()

    def test_defaults(self):
        s = MCPServer(name="fs")
        assert s.id == ""
        assert s.transport == "stdio"
        assert s.args == []
        assert s.env == {}
        assert s.headers == {}
        assert s.discovered_tools == []
        assert s.client is None
        assert s.probe_status is None

    def test_default_collections_are_independent_per_instance(self):
        a = MCPServer(name="a")
        b = MCPServer(name="b")
        a.args.append("x")
        assert b.args == []

    def test_model_copy_with_update(self):
        s = MCPServer(name="fs")
        updated = s.model_copy(update={"probe_status": "found"})
        assert updated.probe_status == "found"
        assert s.probe_status is None  # original untouched

    def test_discovered_tools_accepts_lite_tool_instances(self):
        tool = DiscoveredToolLite(name="read_file")
        s = MCPServer(name="fs", discovered_tools=[tool])
        assert s.discovered_tools[0].name == "read_file"


class TestDiscoveredToolLite:
    def test_requires_name(self):
        with pytest.raises(ValidationError):
            DiscoveredToolLite()

    def test_optional_fields_default_to_none(self):
        t = DiscoveredToolLite(name="x")
        assert t.description is None
        assert t.input_schema is None


class TestTooldexManifest:
    def test_get_server_found(self):
        server = MCPServer(id="a:fs", name="fs")
        manifest = TooldexManifest(
            metadata=TooldexMetadata(name="Test"),
            servers={"a:fs": server},
        )
        assert manifest.get_server("a:fs") is server

    def test_get_server_missing_returns_none(self):
        manifest = TooldexManifest(metadata=TooldexMetadata(name="Test"))
        assert manifest.get_server("nope") is None

    def test_defaults(self):
        manifest = TooldexManifest(metadata=TooldexMetadata(name="Test"))
        assert manifest.servers == {}
        assert manifest.all_tools == []
        assert manifest.server_agents_index == {}
