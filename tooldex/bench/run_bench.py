#!/usr/bin/env python3
"""
tooldex/bench/run_bench.py

Load test: probe N mock MCP servers and report timing.

Usage:
    python -m tooldex.bench.run_bench 100
    python -m tooldex.bench.run_bench 1000 --concurrency 32 --timeout 5
    python -m tooldex.bench.run_bench 500  --delay 0.5   # simulate slow servers

Outputs:
    - Wall time for the full discovery + probe pass
    - Per-server average
    - Theoretical worst-case (N/concurrency × timeout) for comparison
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tooldex.bench.gen_config import gen_config


def run_bench(
    n: int,
    concurrency: int = 16,
    timeout: float = 10.0,
    delay: float = 0.0,
    tools_per_server: int = 3,
) -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp = Path(f.name)

    gen_config(n, tmp, delay=delay, tools_per_server=tools_per_server)

    print(f"\n{'='*64}")
    print(f"  Tooldex load test: {n} servers")
    print(f"  stdio concurrency={concurrency}  timeout={timeout}s  server delay={delay}s")
    print(f"{'='*64}\n")

    start = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable, "-m", "tooldex", "run",
            "--config", str(tmp),
            "--concurrency", str(concurrency),
            "--timeout", str(timeout),
            "--no-cache",
            "--no-serve",
        ],
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start
    tmp.unlink(missing_ok=True)

    print(proc.stdout)
    if proc.returncode != 0 and proc.stderr:
        print("[stderr]", proc.stderr[:600], file=sys.stderr)

    worst_case = (n / concurrency) * max(timeout, delay)
    print(f"\n{'='*64}")
    print(f"  Wall time:            {elapsed:.2f}s")
    print(f"  Per-server avg:       {elapsed / n * 1000:.0f}ms")
    print(f"  Theoretical worst:    {worst_case:.0f}s  (N/concurrency × timeout)")
    print(f"  Efficiency:           {worst_case / elapsed:.1f}x vs worst case")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tooldex load test")
    parser.add_argument("n", type=int, help="Number of mock servers to probe")
    parser.add_argument("--concurrency", "-c", type=int, default=16,
                        help="stdio concurrency (default 16)")
    parser.add_argument("--timeout", "-t", type=float, default=10.0,
                        help="Per-server timeout seconds (default 10)")
    parser.add_argument("--delay", "-d", type=float, default=0.0,
                        help="Simulated server startup delay, seconds (default 0)")
    parser.add_argument("--tools", type=int, default=3,
                        help="Tools per mock server (default 3)")
    args = parser.parse_args()
    run_bench(args.n, args.concurrency, args.timeout, args.delay, args.tools)
