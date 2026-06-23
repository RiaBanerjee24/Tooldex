"""Shared fixtures for the tooldex test suite."""
import pytest

import tooldex.core.parsers.parser as parser_module


@pytest.fixture(autouse=True)
def reset_parser_singleton():
    """The manifest singleton in core/parsers/parser.py is global, mutable
    process state. Reset it around every test so manifest installs in one
    test can't leak into another.
    """
    def _reset():
        parser_module._parser = None
        parser_module._last_scanned = None
        parser_module._startup_time = None
        parser_module._discovery_sources = []

    _reset()
    yield
    _reset()
