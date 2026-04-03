"""
Eval run summary tool.

Parses an adversarial eval JSONL file and prints:
- Per-vector blocked counts and detection rates
- Block attribution (Orchestrator / Security / Query Refinement)
- Total detection rate
- Run ID

Subcommands:
    summary (default):
        python scripts/eval_summary.py <jsonl>
        python scripts/eval_summary.py <jsonl> --token-usage <path>
        python scripts/eval_summary.py <jsonl> --console-log <path>

    validate:
        python scripts/eval_summary.py validate <jsonl>
        python scripts/eval_summary.py validate <jsonl> --dataset <path>
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


EVALS_DIR = Path(__file__).parent.parent / "evals"
DEFAULT_DATASET = EVALS_DIR / "adversarial_queries.json"


def validate_run(
    jsonl_path: Path,
    dataset_path: Path = DEFAULT_DATASET,
) -> bool:
    """
    Validate an eval JSONL for data integrity.

    Checks:
    1. Single run_id across all records
    2. No duplicate query IDs
    3. Full coverage (all non-superseded queries)
    4. No extra IDs not in dataset

    Returns True if all checks pass.
    """
    results = parse_results(jsonl_path=jsonl_path)
    dataset = json.loads(
        dataset_path.read_text(encoding="utf-8")
    )

    ok = True

    # 1. Single run_id
    run_ids = set(r["run_id"] for r in results)
    if len(run_ids) == 1:
        print(f"  [PASS] Single run_id: {run_ids.pop()}")
    else:
        print(f"  [FAIL] Multiple run_ids: {run_ids}")
        ok = False

    # 2. No duplicates
    qids = [r["id"] for r in results]
    dupes = [q for q in set(qids) if qids.count(q) > 1]
    if not dupes:
        print(
            f"  [PASS] {len(qids)} records, "
            f"no duplicates"
        )
    else:
        print(f"  [FAIL] Duplicates: {dupes}")
        ok = False

    # 3. Coverage
    dataset_ids = set(q["id"] for q in dataset)
    superseded = set(
        q["id"] for q in dataset if q.get("superseded")
    )
    expected = dataset_ids - superseded
    result_ids = set(qids)
    missing = expected - result_ids
    if not missing:
        print(
            f"  [PASS] Full coverage: "
            f"{len(expected)} expected, "
            f"{len(result_ids)} found "
            f"({len(superseded)} superseded skipped)"
        )
    else:
        print(
            f"  [FAIL] Missing {len(missing)}: "
            f"{sorted(missing)[:10]}"
        )
        ok = False

    # 4. No extras
    extra = result_ids - dataset_ids
    if not extra:
        print("  [PASS] No extra IDs")
    else:
        print(
            f"  [FAIL] Extra IDs: "
            f"{sorted(extra)[:10]}"
        )
        ok = False

    # 5. Provider IDs check
    all_pids = [
        pid
        for r in results
        for pid in r.get("provider_ids", [])
    ]
    unique_pids = set(all_pids)
    with_pids = sum(
        1 for r in results
        if r.get("provider_ids")
    )
    pipeline_records = sum(
        1 for r in results
        if r["actual_outcome"] in ("allowed", "blocked")
        and r.get("blocking_check") not in (
            "security", "Query Refinement",
        )
    )
    if all_pids:
        dup_pids = len(all_pids) - len(unique_pids)
        print(
            f"  [INFO] provider_ids: "
            f"{len(unique_pids)} unique across "
            f"{with_pids} records "
            f"({pipeline_records} reached LLM)"
        )
        if dup_pids:
            print(
                f"  [WARN] {dup_pids} duplicate "
                f"provider_ids"
            )
    else:
        print(
            "  [INFO] provider_ids: none captured "
            "(pre-Commit 4 run)"
        )

    # Summary
    outcomes = Counter(
        r["actual_outcome"] for r in results
    )
    print(f"\n  Outcomes: {dict(outcomes)}")

    if ok:
        print("\n  RESULT: CLEAN (no contamination)")
    else:
        print("\n  RESULT: ISSUES FOUND")

    return ok


def main():
    """
    Parse arguments and run summary or validate.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Eval run summary and validation tool"
        ),
    )
    parser.add_argument(
        "jsonl_path",
        help="Path to adversarial eval JSONL file",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate JSONL integrity instead of summary",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        help="Path to adversarial_queries.json",
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

    if args.validate:
        ok = validate_run(
            jsonl_path=Path(args.jsonl_path),
            dataset_path=Path(args.dataset),
        )
        sys.exit(0 if ok else 1)

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
