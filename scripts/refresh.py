"""CLI entry point for one scheduled refresh (architecture doc §24).

Runs ingestion, curation, change-driven document reprocessing, and the
post-refresh smoke checks for a domain, then exits non-zero if the result
should not be published.

Usage:
    python scripts/refresh.py --domain vision_zero
    python scripts/refresh.py --domain vision_zero --skip-ingest
    python scripts/refresh.py --domain vision_zero --force-documents
    python scripts/refresh.py --domain vision_zero --json refresh.json
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mocolens import refresh, smoke  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--skip-ingest", action="store_true",
                        help="re-derive artifacts from the raw lake already on disk")
    parser.add_argument("--force-documents", action="store_true",
                        help="reprocess every document, bypassing change detection")
    parser.add_argument("--json", type=Path, default=None,
                        help="also write the full result to this file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    result = refresh.run_refresh(
        args.domain, skip_ingest=args.skip_ingest, force_documents=args.force_documents
    )

    print(f"[{result.domain}]")
    for stage in result.stages:
        print(f"  {stage}")
    print(f"\n{smoke.summarize(result.checks)}")
    for check in result.checks:
        print(f"  {check}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    soft = smoke.failures(result.checks, severity="soft")
    if soft:
        print(f"\nWarnings ({len(soft)}): " + "; ".join(c.name for c in soft))

    print("\nStatus:", "SUCCESS" if result.ok else "FAILED")
    if not result.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
