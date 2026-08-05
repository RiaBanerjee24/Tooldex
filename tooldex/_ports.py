"""tooldex/_ports.py — finds a free port to bind the UI server to."""
import socket

import typer

PORT_DEFAULT = 8282
_PORT_HARD_LIMIT = 49150

_SKIP_PORTS: frozenset[int] = frozenset({
    *range(0, 1024),
    3000, 3001,
    3306,
    4200,
    5000, 5001,
    5173,
    5432,
    6379,
    8000, 8001,
    8080, 8081,
    8443,
    8888,
    9000,
    9090,
    9092,
    9200,
    27017,
})


def find_free_port(start: int, host: str) -> int:
    port = start
    while port <= _PORT_HARD_LIMIT:
        if port not in _SKIP_PORTS:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind((host, port))
                    return port
                except OSError:
                    pass
        port += 1
    typer.echo(f"\n  Error: No free port found between {start} and {_PORT_HARD_LIMIT}.\n", err=True)
    raise typer.Exit(1)
