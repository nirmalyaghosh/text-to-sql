"""
Demo: Schema pruning benchmark against golden queries.

Usage:
    python demos/05_schema_pruning_benchmark.py
    python demos/05_schema_pruning_benchmark.py --verbose
    python demos/05_schema_pruning_benchmark.py --query GQ-002

Runs each prunable golden query through the deterministic SchemaPruner,
measures token reduction, and computes precision/recall against expected
tables. No LLM calls — fully reproducible.
"""

import argparse
import json
import logging
import statistics
from pathlib import Path
from typing import Dict, List, Set

from text_to_sql.app_logger import get_logger, setup_logging
from text_to_sql.schema_pruner import SchemaPruner


logger = get_logger(__name__)

EVALS_DIR = Path(__file__).parent.parent / "evals"
SCHEMA_DIR = Path(__file__).parent.parent / "schema"


def compute_precision_recall(
    selected: Set[str],
    expected: Set[str],
) -> Dict[str, float]:
    """
    Compute precision and recall for table selection.
    """
    if not expected:
        return {"precision": 1.0, "recall": 1.0}
    if not selected:
        return {"precision": 0.0, "recall": 0.0}

    true_positives = len(selected & expected)
    precision = true_positives / len(selected) if selected else 0.0
    recall = true_positives / len(expected) if expected else 0.0
    return {"precision": precision, "recall": recall}


def format_table_row(
    query_id: str,
    nl_query: str,
    full_tokens: int,
    pruned_tokens: int,
    reduction_pct: float,
    selected: List[str],
    expected: List[str],
    precision: float,
    recall: float,
    verbose: bool = False,
) -> str:
    """
    Format a single benchmark row for display.
    """
    status = "PASS" if recall >= 0.8 else "FAIL"
    line = (
        f"  {query_id}  {status}  "
        f"{full_tokens:>5,} -> {pruned_tokens:>4,}  "
        f"({reduction_pct:5.1f}%)  "
        f"P={precision:.2f}  R={recall:.2f}"
    )
    if verbose:
        line += f"\n         Q: {nl_query}"
        line += f"\n         Expected:  {sorted(expected)}"
        line += f"\n         Selected:  {sorted(selected)}"
        missing = set(expected) - set(selected)
        extra = set(selected) - set(expected)
        if missing:
            line += f"\n         Missing:   {sorted(missing)}"
        if extra:
            line += f"\n         Extra:     {sorted(extra)}"
    return line


def load_golden_queries() -> List[Dict]:
    """
    Load golden queries from evals directory.
    """
    path = EVALS_DIR / "golden_queries.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema_ddl() -> str:
    """
    Load full schema DDL from schema directory.
    """
    path = SCHEMA_DIR / "schema_setup.sql"
    return path.read_text(encoding="utf-8")


def run_benchmark(
    verbose: bool = False,
    query_filter: str | None = None,
) -> None:
    """
    Run schema pruning benchmark against golden queries.
    """
    # Suppress pruner's per-query log lines during benchmark
    logging.getLogger("text_to_sql.schema_pruner").setLevel(
        logging.WARNING
    )

    ddl = load_schema_ddl()
    pruner = SchemaPruner(ddl)
    golden_queries = load_golden_queries()

    # Filter to prunable queries (allowed outcome with expected tables)
    prunable = [
        gq for gq in golden_queries
        if gq["expected_outcome"] == "allowed"
        and gq["expected_tables"]
    ]

    if query_filter:
        prunable = [
            gq for gq in prunable
            if gq["id"] == query_filter
        ]
        if not prunable:
            logger.info(f"No prunable query found with ID: {query_filter}")
            return

    logger.info(f"Schema pruning benchmark: {len(prunable)} queries")
    logger.info(f"Full schema: {len(pruner._all_tables)} tables")
    logger.info("")
    logger.info(
        "  ID      Status  Tokens              Reduction  "
        "Precision  Recall"
    )
    logger.info("  " + "-" * 70)

    reductions = []
    precisions = []
    recalls = []
    total_full_tokens = 0
    total_pruned_tokens = 0
    failures = []

    for gq in prunable:
        result = pruner.prune(gq["nl_query"], max_depth=0)
        expected = set(gq["expected_tables"])
        selected = set(result.selected_tables)

        metrics = compute_precision_recall(selected, expected)
        precision = metrics["precision"]
        recall = metrics["recall"]

        reductions.append(result.reduction_pct)
        precisions.append(precision)
        recalls.append(recall)
        total_full_tokens += result.full_schema_tokens
        total_pruned_tokens += result.pruned_schema_tokens

        if recall < 0.8:
            failures.append(gq["id"])

        row = format_table_row(
            query_id=gq["id"],
            nl_query=gq["nl_query"],
            full_tokens=result.full_schema_tokens,
            pruned_tokens=result.pruned_schema_tokens,
            reduction_pct=result.reduction_pct,
            selected=result.selected_tables,
            expected=gq["expected_tables"],
            precision=precision,
            recall=recall,
            verbose=verbose,
        )
        logger.info(row)

    if not prunable:
        return

    # Summary
    logger.info("")
    logger.info("  Summary")
    logger.info("  " + "-" * 70)
    logger.info(
        f"  Queries:          {len(prunable)}"
    )
    logger.info(
        f"  Mean reduction:   {statistics.mean(reductions):5.1f}%"
    )
    logger.info(
        f"  Median reduction: {statistics.median(reductions):5.1f}%"
    )
    logger.info(
        f"  Mean precision:   {statistics.mean(precisions):.2f}"
    )
    logger.info(
        f"  Mean recall:      {statistics.mean(recalls):.2f}"
    )
    logger.info(
        f"  Token savings:    "
        f"{total_full_tokens:,} -> {total_pruned_tokens:,} "
        f"({total_full_tokens - total_pruned_tokens:,} saved)"
    )

    if failures:
        logger.info(
            f"  Failures (R<0.8): {', '.join(failures)}"
        )
    else:
        logger.info(
            f"  Failures (R<0.8): none"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Schema pruning benchmark for Text-to-SQL"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show per-query details (tables selected vs expected)"
    )
    parser.add_argument(
        "--query", type=str, default=None,
        help="Run benchmark for a single query ID (e.g. GQ-002)"
    )
    args = parser.parse_args()

    setup_logging()
    run_benchmark(verbose=args.verbose, query_filter=args.query)
