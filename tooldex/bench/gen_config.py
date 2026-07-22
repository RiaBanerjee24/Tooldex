#!/usr/bin/env python3
"""
tooldex/bench/gen_config.py

Generate a temporary MCP config with N mock servers for benchmarking.

Usage:
    python -m tooldex.bench.gen_config 100
    python -m tooldex.bench.gen_config 1000 --output /tmp/big.json --delay 0.2
"""
import argparse
import json
import sys
from pathlib import Path


def gen_config(
    n: int,
    output: Path,
    delay: float = 0.0,
    tools_per_server: int = 5,
) -> None:
    mock = Path(__file__).parent / "mock_server.py"
    servers = {
        f"mock_{i:05d}": {
            "command": sys.executable,
            "args": [str(mock), "--tools", str(tools_per_server), "--delay", str(delay)],
        }
        for i in range(n)
    }
    output.write_text(json.dumps({"mcpServers": servers}, indent=2))
    print(f"Generated {n}-server config → {output}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate benchmark MCP config")
    parser.add_argument("n", type=int, help="Number of mock servers")
    parser.add_argument("--output", type=Path, default=Path("/tmp/tooldex_bench.json"))
    parser.add_argument("--delay", type=float, default=0.0, help="Per-server startup delay (s)")
    parser.add_argument("--tools", type=int, default=5, help="Tools per server")
    args = parser.parse_args()
    gen_config(args.n, args.output, args.delay, args.tools)
    print(args.output)
