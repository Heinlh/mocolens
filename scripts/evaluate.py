"""CLI entry point for the agent evaluation harness.

Runs evals/questions.yaml through the scope gate and the real agent, prints a
scorecard, and writes every question's full record to logs/evals/.

This calls the real, billed model: about fifty questions at a few tool calls
each. Needs AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT (.env).

Usage:
    python scripts/evaluate.py
    python scripts/evaluate.py --category structured
    python scripts/evaluate.py --id s01-pedestrian-2025 --id d01-school-bus-citations
    python scripts/evaluate.py --limit 5 --workers 1
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mocolens import evaluation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=evaluation.CATEGORIES, action="append")
    parser.add_argument("--id", action="append", help="run only this case (repeatable)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=3,
                        help="questions in flight at once; latencies are measured under this load")
    args = parser.parse_args()

    cases = evaluation.load_cases()
    if args.category:
        cases = [c for c in cases if c["category"] in args.category]
    if args.id:
        cases = [c for c in cases if c["id"] in args.id]
    cases = cases[:args.limit]
    if not cases:
        raise SystemExit("No cases match.")

    # The API module turns on INFO logging for the server; here it would bury
    # the scorecard under one line per HTTP call.
    logging.disable(logging.INFO)

    print(f"Running {len(cases)} question(s), {args.workers} at a time...\n")
    results = evaluation.run(cases, workers=args.workers)
    print(evaluation.summarize(results))
    print(f"\nFull records: {evaluation.save(results)}")


if __name__ == "__main__":
    main()
