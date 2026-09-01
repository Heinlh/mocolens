"""CLI entry point for the processing layer.

Usage:
    python scripts/rebuild_vector_index.py --domain vision_zero
    python scripts/rebuild_vector_index.py --domain vision_zero --force
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mocolens.processing import runner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    stats = runner.process_domain(args.domain, force=args.force)

    print(f"[{args.domain}]")
    print(f"Documents processed: {stats['documents_processed']}")
    print(f"Documents skipped (already chunked): {stats['documents_skipped']}")
    print(f"Documents failed: {stats['documents_failed']}")
    print(f"Chunks embedded: {stats['chunks_created']}")
    if stats["documents_failed"]:
        print("See logs/ingestion/processing_failures.jsonl for tracebacks.")
    print("Status:", "PARTIAL FAILURE" if stats["documents_failed"] else "SUCCESS")


if __name__ == "__main__":
    main()
