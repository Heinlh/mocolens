"""CLI entry point for the structured transform layer.

Usage:
    python scripts/build_curated_tables.py --domain vision_zero
    python scripts/build_curated_tables.py --domain vision_zero --snapshot-date 2026-08-30
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mocolens.processing import curate  # noqa: E402
from mocolens.processing.quality import QualityError  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--snapshot-date", default=None, help="YYYY-MM-DD; defaults to the latest available snapshot")
    args = parser.parse_args()

    try:
        result = curate.curate_domain(args.domain, snapshot_date=args.snapshot_date)
    except QualityError as exc:
        print(f"[{args.domain}] Status: FAILED - hard quality check failed: {exc}")
        raise SystemExit(1)
    except (ValueError, FileNotFoundError) as exc:
        print(f"[{args.domain}] Status: FAILED - {exc}")
        raise SystemExit(1)

    print(f"[{args.domain}]")
    print(f"Snapshot: {result['snapshot_dir']}")
    for table, count in result["row_counts"].items():
        print(f"{table}: {count:,} rows")

    checks = result["quality_report"]["checks"]
    violations = [c for c in checks if c["violations"] > 0]
    if violations:
        print(f"\nQuality checks with violations ({len(violations)}/{len(checks)}):")
        for c in violations:
            print(f"  [{c['severity']}] {c['name']}: {c['violations']} - {c['detail']}")
    else:
        print(f"\nAll {len(checks)} quality checks passed clean.")

    print("Status: SUCCESS")


if __name__ == "__main__":
    main()
