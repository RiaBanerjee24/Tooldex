#!/usr/bin/env python3
"""
tooldex/bench/mock_server.py

Minimal MCP stdio server for load testing.
Responds to initialize + tools/list instantly, then idles.

Usage (standalone):
    python tooldex/bench/mock_server.py --tools 10 --delay 0.5

Options:
    --tools   N   Number of fake tools to expose (default 5)
    --delay   S   Seconds to sleep before accepting connections (default 0)
"""
import argparse
import asyncio


async def main(n_tools: int, delay: float) -> None:
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        import mcp.types as types
    except ImportError:
        raise SystemExit("mcp package is required: pip install mcp")

    if delay > 0:
        await asyncio.sleep(delay)

    app = Server("mock-bench")

    @app.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name=f"tool_{i:04d}",
                description=f"Synthetic benchmark tool {i}.",
                inputSchema={"type": "object", "properties": {}},
            )
            for i in range(n_tools)
        ]

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock MCP server for benchmarking")
    parser.add_argument("--tools", type=int, default=5, help="Number of tools to expose")
    parser.add_argument("--delay", type=float, default=0.0, help="Startup delay in seconds")
    args = parser.parse_args()
    asyncio.run(main(args.tools, args.delay))
