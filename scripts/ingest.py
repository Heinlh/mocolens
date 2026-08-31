"""CLI entry point for the extract layer.

Usage:
    python scripts/ingest.py --domain vision_zero
    python scripts/ingest.py --domain vision_zero --documents-only
    python scripts/ingest.py --domain vision_zero --api-only
    python scripts/ingest.py --domain vision_zero --force
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mocolens.ingestion import runner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--documents-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = runner.run(
        args.domain,
        api_only=args.api_only,
        documents_only=args.documents_only,
        force=args.force,
    )

    print(f"[{result['domain']}]")
    if "api" in result:
        print(f"API sources checked: {result['api']['sources_checked']}")
        print(f"API records downloaded: {result['api']['records_downloaded']}")
    if "documents" in result:
        d = result["documents"]
        print(f"Documents discovered: {d['discovered']}")
        print(f"New documents: {d['new']}")
        print(f"Changed documents: {d['changed']}")
        print(f"Documents skipped: {d['skipped']}")
    print("Status: SUCCESS")


if __name__ == "__main__":
    main()
