"""
Demo: Ablation study for the 3-layer entity resolver.

Usage:
    python demos/05_schema_pruning_ablation_study.py
    python demos/05_schema_pruning_ablation_study.py --verbose

Measures each resolver layer's contribution to
precision and recall by running all prunable golden
queries through three configurations:

  L1        Direct table name matching only
  L1+L2     + Business entity mapping (ENTITY_MAP)
  L1+L2+L3  + Column name matching (full resolver)

No LLM calls - fully reproducible.
"""

import argparse
import json
import logging
import statistics

from pathlib import Path
from typing import (
    Dict,
    List,
    Set,
    Tuple,
)

from text_to_sql.app_logger import (
    get_logger,
    setup_logging,
)
from text_to_sql.schema_pruner import SchemaPruner


logger = get_logger(__name__)

CONFIGS: List[Tuple[str, int]] = [
    ("L1", 1),
    ("L1+L2", 2),
    ("L1+L2+L3", 3),
]
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
    precision = (
        true_positives / len(selected)
        if selected else 0.0
    )
    recall = (
        true_positives / len(expected)
        if expected else 0.0
    )
    return {"precision": precision, "recall": recall}


def load_golden_queries() -> List[Dict]:
    """
    Load golden queries from evals directory.
    """
    path = EVALS_DIR / "golden_queries.json"
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def load_schema_ddl() -> str:
    """
    Load full schema DDL from schema directory.
    """
    path = SCHEMA_DIR / "schema_setup.sql"
    return path.read_text(encoding="utf-8")


def run_ablation(verbose: bool = False) -> None:
    """
    Run ablation study across all three layer
    configurations and print comparison table.
    """
    # Suppress pruner's per-query log lines
    logging.getLogger(
        "text_to_sql.schema_pruner"
    ).setLevel(logging.WARNING)

    ddl = load_schema_ddl()
    pruner = SchemaPruner(ddl)
    golden_queries = load_golden_queries()

    # Filter to prunable queries
    prunable = [
        gq for gq in golden_queries
        if gq["expected_outcome"] == "allowed"
        and gq["expected_tables"]
    ]

    logger.info(
        "Ablation study: 3-layer entity resolver"
    )
    logger.info(f"Queries: {len(prunable)}")
    logger.info("")

    # Collect results per configuration
    config_results: Dict[str, Dict] = {}

    for config_name, max_layers in CONFIGS:
        precisions = []
        recalls = []
        failures = []

        if verbose:
            logger.info(
                f"  --- {config_name} "
                f"(max_layers={max_layers}) ---"
            )

        for gq in prunable:
            query = gq["nl_query"]
            expected = set(gq["expected_tables"])

            seeds = pruner.resolve_tables(
                query, max_layers=max_layers
            )
            selected = pruner.find_minimal_tables(
                seeds, max_depth=0
            )

            metrics = compute_precision_recall(
                selected, expected
            )
            p = metrics["precision"]
            r = metrics["recall"]
            precisions.append(p)
            recalls.append(r)

            if r < 1.0:
                failures.append(gq["id"])

            if verbose:
                status = (
                    "PASS" if r >= 1.0 else "FAIL"
                )
                line = (
                    f"  {gq['id']}  {status}  "
                    f"P={p:.2f}  R={r:.2f}"
                )
                logger.info(line)
                missing = expected - selected
                extra = selected - expected
                if missing:
                    logger.info(
                        f"         Missing: "
                        f"{sorted(missing)}"
                    )
                if extra:
                    logger.info(
                        f"         Extra:   "
                        f"{sorted(extra)}"
                    )

        config_results[config_name] = {
            "mean_p": statistics.mean(precisions),
            "mean_r": statistics.mean(recalls),
            "fail_count": len(failures),
            "failures": failures,
        }

        if verbose:
            logger.info("")

    # Print comparison table
    logger.info("  Comparison Table")
    logger.info("  " + "-" * 52)
    logger.info(
        "  Config       Mean P   Mean R   "
        "Queries w/ R<1.0"
    )
    logger.info("  " + "-" * 52)

    for config_name, _ in CONFIGS:
        r = config_results[config_name]
        logger.info(
            f"  {config_name:<12} "
            f"{r['mean_p']:>6.2f}   "
            f"{r['mean_r']:>6.2f}   "
            f"{r['fail_count']:>2}/{len(prunable)}"
        )

    logger.info("  " + "-" * 52)
    logger.info("")

    # Interpretation
    l1 = config_results["L1"]
    l12 = config_results["L1+L2"]
    l123 = config_results["L1+L2+L3"]

    if l12["mean_r"] > l1["mean_r"]:
        r_gain = l12["mean_r"] - l1["mean_r"]
        logger.info(
            f"  Layer 2 (ENTITY_MAP) adds "
            f"+{r_gain:.2f} recall "
            f"({l1['fail_count']} -> "
            f"{l12['fail_count']} failures)"
        )
    if l123["mean_p"] != l12["mean_p"]:
        p_delta = l123["mean_p"] - l12["mean_p"]
        sign = "+" if p_delta > 0 else ""
        logger.info(
            f"  Layer 3 (column matching) "
            f"{sign}{p_delta:.2f} precision, "
            f"no recall change"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Ablation study for schema pruner "
            "entity resolver"
        )
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-query detail for each config",
    )
    args = parser.parse_args()

    setup_logging()
    run_ablation(verbose=args.verbose)
