"""Unit tests for tooldex/_ports.py."""
import socket

import pytest
import typer

from tooldex._ports import find_free_port


class TestFindFreePort:
    def test_returns_start_port_when_free(self):
        # pick a high, unlikely-to-be-skipped port
        assert find_free_port(41000, "127.0.0.1") == 41000

    def test_skips_an_occupied_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(("127.0.0.1", 41010))
            occupied.listen(1)
            result = find_free_port(41010, "127.0.0.1")
        assert result != 41010
        assert result > 41010

    def test_skips_ports_in_the_skip_list(self):
        # 3000 and 3001 are both in _SKIP_PORTS
        result = find_free_port(3000, "127.0.0.1")
        assert result not in (3000, 3001)

    def test_skips_privileged_port_range(self):
        result = find_free_port(0, "127.0.0.1")
        assert result >= 1024

    def test_raises_typer_exit_when_no_port_available(self, monkeypatch):
        import tooldex._ports as ports_module
        monkeypatch.setattr(ports_module, "_PORT_HARD_LIMIT", 41099)
        # occupy the only allowed port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(("127.0.0.1", 41099))
            occupied.listen(1)
            with pytest.raises(typer.Exit):
                find_free_port(41099, "127.0.0.1")
