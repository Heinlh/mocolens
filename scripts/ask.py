"""CLI entry point for the LangGraph agent.

Usage:
    python scripts/ask.py "Have pedestrian crashes increased in Silver Spring since 2022?"

Requires WATSONX_APIKEY, WATSONX_URL, WATSONX_PROJECT_ID - copy .env.example
to .env at the repo root and fill them in.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mocolens.agent.graph import ask  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/ask.py \"<question>\"")
        raise SystemExit(1)

    question = sys.argv[1]
    print(f"Q: {question}\n")

    try:
        answer = ask(question)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)

    print(f"ANSWER: {answer.answer}\n")
    print(f"SUMMARY: {answer.summary}\n")
    print(f"WHAT IT MEANS: {answer.what_data_means}\n")
    if answer.county_report_points:
        print("WHAT COUNTY REPORTS SAY:")
        for point in answer.county_report_points:
            print(f"  - {point}")
        print()
    if answer.caveats:
        print("CAVEATS:")
        for caveat in answer.caveats:
            print(f"  - {caveat}")
        print()
    if answer.citations:
        print("CITATIONS:")
        for c in answer.citations:
            page = f", p.{c.page}" if c.page else ""
            print(f"  - {c.title} ({c.source_type}{page}) {c.url or ''}")
        print()
    if answer.follow_up_prompts:
        print("FOLLOW-UP PROMPTS:")
        for prompt in answer.follow_up_prompts:
            print(f"  - {prompt}")


if __name__ == "__main__":
    main()
