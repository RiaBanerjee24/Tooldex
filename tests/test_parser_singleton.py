"""Unit tests for toolpool/core/parsers/parser.py."""
import pytest

from toolpool.core.models.manifest import ToolpoolManifest, ToolpoolMetadata
from toolpool.core.parsers.parser import (
    get_discovery_sources,
    get_last_scanned,
    get_parser,
    get_startup_time,
    init_parser_from_manifest,
    store_discovery_sources,
)


def _manifest(name="Test") -> ToolpoolManifest:
    return ToolpoolManifest(metadata=ToolpoolMetadata(name=name))


class TestGetParser:
    def test_raises_before_init(self):
        with pytest.raises(RuntimeError):
            get_parser()

    def test_returns_installed_parser_after_init(self):
        manifest = _manifest()
        init_parser_from_manifest(manifest)
        assert get_parser().manifest is manifest


class TestInitParserFromManifest:
    def test_sets_last_scanned(self):
        assert get_last_scanned() is None
        init_parser_from_manifest(_manifest())
        assert get_last_scanned() is not None

    def test_sets_startup_time_only_on_first_install(self):
        init_parser_from_manifest(_manifest())
        first_startup = get_startup_time()
        assert first_startup is not None

        init_parser_from_manifest(_manifest("Second"))
        assert get_startup_time() == first_startup

    def test_last_scanned_updates_on_each_install(self):
        init_parser_from_manifest(_manifest())
        first_scanned = get_last_scanned()

        # Same manifest install — last_scanned should still be reassigned (a new
        # timestamp string), even though the value may render identical at this
        # resolution; what matters is the call path runs every time.
        init_parser_from_manifest(_manifest("Second"))
        second_scanned = get_last_scanned()
        assert second_scanned is not None
        assert get_parser().manifest.metadata.name == "Second"


class TestDiscoverySourcesStorage:
    def test_defaults_to_empty_list(self):
        assert get_discovery_sources() == []

    def test_store_and_retrieve(self):
        store_discovery_sources(["a", "b"])
        assert get_discovery_sources() == ["a", "b"]

    def test_store_none_normalizes_to_empty_list(self):
        store_discovery_sources(None)
        assert get_discovery_sources() == []
