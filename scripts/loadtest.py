"""Latency under load for one endpoint: fire N requests at a fixed concurrency
and print the status mix and p50/p95/p99. Standard library only.

Usage:
    python scripts/loadtest.py http://localhost:8001/api/dashboard/summary
    python scripts/loadtest.py http://localhost:8001/api/dashboard/map -n 300 -c 25 --vary-client
    python scripts/loadtest.py http://localhost:8001/api/query -n 6 -c 6 \
        --post '{"question": "How many crashes involved pedestrians in 2025?"}'

Every /api/query request is a real, billed agent run - keep -n small there.

--vary-client sends a different X-Forwarded-For per request. Without it the
whole run is one visitor and the per-IP rate limit answers 429 after the
first sixty requests, which measures the limiter rather than the endpoint.
"""
import argparse
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def hit(url: str, body: str | None, client: str | None) -> tuple[int, float]:
    headers = {"Content-Type": "application/json"} if body else {}
    if client:
        headers["X-Forwarded-For"] = client
    request = urllib.request.Request(url, data=body.encode() if body else None, headers=headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except OSError:
        status = 0  # refused, reset, or timed out
    return status, (time.perf_counter() - started) * 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("-n", "--requests", type=int, default=200)
    parser.add_argument("-c", "--concurrency", type=int, default=10)
    parser.add_argument("--post", default=None, help="JSON body; sends POST instead of GET")
    parser.add_argument("--vary-client", action="store_true")
    args = parser.parse_args()

    clients = [f"198.51.{i // 250}.{i % 250 + 1}" if args.vary_client else None for i in range(args.requests)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda client: hit(args.url, args.post, client), clients))
    elapsed = time.perf_counter() - started

    statuses = Counter(status for status, _ in results)
    print(f"{args.requests} requests, {args.concurrency} at a time, {elapsed:.1f}s "
          f"({args.requests / elapsed:.1f} req/s)")
    print("status: " + ", ".join(f"{code or 'failed'} x{count}" for code, count in sorted(statuses.items())))
    # Percentiles over successes only: a 429 returns in a millisecond and
    # would make the endpoint look faster the more it is overloaded.
    ok = sorted(ms for status, ms in results if status == 200)
    if len(ok) >= 2:
        cuts = statistics.quantiles(ok, n=100, method="inclusive")
        print(f"200s:   p50 {cuts[49]:.0f} ms   p95 {cuts[94]:.0f} ms   p99 {cuts[98]:.0f} ms   max {ok[-1]:.0f} ms")


if __name__ == "__main__":
    main()
