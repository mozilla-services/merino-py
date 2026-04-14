"""Quick latency benchmark for query normalization.

Fires N requests with and without the variant and compares response times.

Usage:
    cd /Users/Vbaungally/Desktop/moz/merino-py
    uv run python tests/manual/bench_normalization.py

Requires: server running on localhost:8000 with normalization enabled.
"""

import csv
import random
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000/api/v1/suggest"
VARIANT = "query_norm_treatment"
GOLDEN_SET = Path.home() / "Downloads" / "golden_set.csv"
N_QUERIES = 500


def load_queries() -> list[str]:
    """Sample queries from golden set weighted by session count."""
    queries: list[tuple[str, int]] = []
    with open(GOLDEN_SET) as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = row["final_query"].strip()
            if q and len(q) > 2:
                queries.append((q, int(row["session_count"])))

    population = [q for q, _ in queries]
    weights = [w for _, w in queries]
    return random.choices(population, weights=weights, k=N_QUERIES)


def bench(client: httpx.Client, queries: list[str], use_variant: bool) -> list[float]:
    """Run queries and return per-request latencies in ms."""
    latencies: list[float] = []
    for q in queries:
        params: dict[str, str] = {"q": q}
        if use_variant:
            params["client_variants"] = VARIANT

        start = time.perf_counter()
        resp = client.get(BASE, params=params)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

        if resp.status_code != 200:
            print(f"  WARN: {resp.status_code} for q={q[:30]}")

    return latencies


def stats(latencies: list[float]) -> dict[str, float]:
    """Compute summary stats."""
    s = sorted(latencies)
    n = len(s)
    return {
        "mean": sum(s) / n,
        "p50": s[n // 2],
        "p95": s[int(n * 0.95)],
        "p99": s[int(n * 0.99)],
        "min": s[0],
        "max": s[-1],
    }


def main() -> None:
    """Run the benchmark."""
    print(f"Loading {N_QUERIES} queries from golden set...")
    queries = load_queries()
    print(f"Loaded {len(queries)} queries")

    client = httpx.Client(timeout=10.0)

    # Warmup
    print("Warming up (10 requests)...")
    for q in queries[:10]:
        client.get(BASE, params={"q": q})
        client.get(BASE, params={"q": q, "client_variants": VARIANT})

    # Control (no normalization)
    print(f"\nRunning {N_QUERIES} control requests (no variant)...")
    control = bench(client, queries, use_variant=False)
    control_stats = stats(control)

    # Treatment (with normalization)
    print(f"Running {N_QUERIES} treatment requests (with variant)...")
    treatment = bench(client, queries, use_variant=True)
    treatment_stats = stats(treatment)

    client.close()

    # Report
    print("\n" + "=" * 60)
    print(f"{'Metric':<10} {'Control (ms)':>15} {'Treatment (ms)':>15} {'Overhead':>10}")
    print("-" * 60)
    for key in ["mean", "p50", "p95", "p99", "min", "max"]:
        c = control_stats[key]
        t = treatment_stats[key]
        overhead = t - c
        print(f"{key:<10} {c:>15.2f} {t:>15.2f} {overhead:>+10.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
