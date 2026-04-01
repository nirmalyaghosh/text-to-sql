"""
Eval run summary tool.

Parses an adversarial eval JSONL file and prints:
- Per-vector blocked counts and detection rates
- Block attribution (Orchestrator / Security / Query Refinement)
- Total detection rate
- Run ID

Optionally computes cost from token_usage.jsonl using the run ID.

Usage:
    python scripts/eval_summary.py <jsonl_path>
    python scripts/eval_summary.py <jsonl_path> --token-usage <token_usage_path>
    python scripts/eval_summary.py <jsonl_path> --console-log <log_path>
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def parse_results(jsonl_path: Path) -> list[dict]:
    """
    Helper function used to load results from a JSONL file.
    """
    results = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            results.append(json.loads(line))
    return results


def compute_summary(results: list[dict]) -> dict:
    """
    Helper function used to compute per-vector and
    overall detection stats from eval results.
    """
    vectors = {}
    blocking_checks = Counter()
    run_id = None
    total_blocked = 0
    total_executed = 0

    for r in results:
        if run_id is None:
            run_id = r.get("run_id")

        if r["actual_outcome"] == "skipped":
            continue

        v = r["vector"]
        total_executed += 1

        if v not in vectors:
            vectors[v] = {"blocked": 0, "total": 0}
        vectors[v]["total"] += 1

        if r["actual_outcome"] == "blocked":
            vectors[v]["blocked"] += 1
            total_blocked += 1
            check = r.get("blocking_check", "unknown")
            blocking_checks[check] += 1

    return {
        "run_id": run_id,
        "vectors": vectors,
        "blocking_checks": dict(
            blocking_checks.most_common()
        ),
        "total_blocked": total_blocked,
        "total_executed": total_executed,
    }


def compute_cost(
    token_usage_path: Path,
    run_id: str,
) -> dict:
    """
    Helper function used to compute token counts and
    cost for a given run ID from token_usage.jsonl.

    Uses gpt-4o-mini rates as default. Actual cost
    should be verified against OpenRouter activity.
    """
    total_input = 0
    total_output = 0
    call_count = 0

    with open(token_usage_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if not r.get(
                "request_id", ""
            ).startswith(run_id):
                continue
            if (
                r["event"] == "llm_response"
                and "usage" in r
            ):
                total_input += r["usage"]["prompt_tokens"]
                total_output += r["usage"][
                    "completion_tokens"
                ]
                call_count += 1

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "call_count": call_count,
    }


def count_errors(console_log_path: Path) -> int:
    """
    Helper function used to count 429 and quota
    errors in a console log file.
    """
    count = 0
    with open(console_log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "429" in line or "insufficient_quota" in line:
                count += 1
    return count


def print_summary(
    summary: dict,
    cost: dict | None = None,
    error_count: int | None = None,
) -> None:
    """
    Helper function used to print the eval summary
    in a readable format.
    """
    print("=" * 60)
    print(f"  Run ID: {summary['run_id']}")
    print("=" * 60)

    print("\n  Per-vector detection:")
    for v in sorted(summary["vectors"]):
        s = summary["vectors"][v]
        b = s["blocked"]
        t = s["total"]
        pct = 100 * b / t if t > 0 else 0
        print(f"    {v:25s}: {b}/{t} ({pct:.1f}%)")

    tb = summary["total_blocked"]
    te = summary["total_executed"]
    pct = 100 * tb / te if te > 0 else 0
    print(f"\n  Total: {tb}/{te} ({pct:.1f}%)")

    print("\n  Block attribution:")
    for check, count in summary["blocking_checks"].items():
        print(f"    {check}: {count}")

    if cost:
        print(f"\n  LLM calls: {cost['call_count']}")
        print(f"  Input tokens: {cost['input_tokens']:,}")
        print(f"  Output tokens: {cost['output_tokens']:,}")

    if error_count is not None:
        print(f"\n  429/quota errors: {error_count}")

    print()


def main():
    """
    Parse arguments and run the eval summary.
    """
    parser = argparse.ArgumentParser(
        description="Eval run summary tool"
    )
    parser.add_argument(
        "jsonl_path",
        help="Path to adversarial eval JSONL file",
    )
    parser.add_argument(
        "--token-usage",
        help="Path to token_usage.jsonl for cost",
    )
    parser.add_argument(
        "--console-log",
        help="Path to console log for 429 count",
    )
    args = parser.parse_args()

    results = parse_results(
        jsonl_path=Path(args.jsonl_path)
    )
    summary = compute_summary(results=results)

    cost = None
    if args.token_usage and summary["run_id"]:
        cost = compute_cost(
            token_usage_path=Path(args.token_usage),
            run_id=summary["run_id"],
        )

    error_count = None
    if args.console_log:
        error_count = count_errors(
            console_log_path=Path(args.console_log),
        )

    print_summary(
        summary=summary,
        cost=cost,
        error_count=error_count,
    )


if __name__ == "__main__":
    main()
