"""
Ablation study: measure contribution of each agent.

Runs golden queries through 4 pipeline configurations:
  (a) full        -- all agents + self-critique
  (b) no_security -- skip Security Agent
  (c) no_refine   -- skip Refinement Agent
  (d) no_critique -- SQL Gen without self-critique loop

For each query x config, records per-agent metrics,
ground-truth comparison (precision/recall on table
selection, expected_outcome matching), and SQL
execution results.

Output:
  evals/ablation_YYYYMMDD_HHMMSS.jsonl
    One JSON record per (query, config) pair.
    Every record contains the full execution chain,
    per-agent details, ground-truth comparison, and
    SQL execution result.

Usage:
    uv run python -m demos.06_agentic_ablation_study
    uv run python -m demos.06_agentic_ablation_study --verbose
    uv run python -m demos.06_agentic_ablation_study --query GQ-002
"""

import argparse
import asyncio
import json
import logging
import re
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
)

from dotenv import load_dotenv

from text_to_sql.agents import (
    OrchestratorAgent,
    QueryRequest,
)
from text_to_sql.agents.types import (
    AgenticResponse,
    ExecutionChainStep,
    SQLCritique,
)
from text_to_sql.agents.query_refinement import (
    QueryRefinementAgent,
)
from text_to_sql.agents.schema_intelligence import (
    SchemaIntelligenceAgent,
)
from text_to_sql.agents.security_governance import (
    SecurityGovernanceAgent,
)
from text_to_sql.agents.sql_generation import (
    SQLGenerationAgent,
)
from text_to_sql.app_logger import (
    get_logger,
    setup_logging,
)
from text_to_sql.db import execute_query


logger = get_logger(__name__)

EVALS_DIR = Path(__file__).parent.parent / "evals"
REF_DATE = datetime(2026, 2, 22)
CONFIGS = [
    "full", "no_security", "no_refine", "no_critique",
]


# ---- NoCritique variant ----


class NoCritiqueSQLGenAgent(SQLGenerationAgent):
    """
    SQL Generation without the self-critique LLM call.

    Overrides _critique_sql to always accept the first
    generation attempt. Isolates the critique loop's
    contribution.
    """

    async def _critique_sql(
        self,
        sql: str,
        schema: str,
        query: str,
    ) -> SQLCritique:
        return SQLCritique(
            is_valid=True,
            issues=[],
            corrected_sql=None,
        )


# ---- Loading & filtering ----


def load_golden_queries() -> List[Dict[str, Any]]:
    """
    Load golden queries from evals directory.
    """
    path = EVALS_DIR / "golden_queries.json"
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def filter_golden_queries(
    golden_queries: List[Dict[str, Any]],
    query_filter: Optional[str],
) -> Optional[List[Dict[str, Any]]]:
    """
    Apply optional ID filter to golden queries.

    Returns None (with a warning) when the filter
    matches nothing, so the caller can bail out early.
    """
    if not query_filter:
        return golden_queries
    filtered = [
        gq for gq in golden_queries
        if gq["id"] == query_filter
    ]
    if not filtered:
        logger.warning(
            f"No query found with ID: "
            f"{query_filter}"
        )
        return None
    return filtered


# ---- Metrics helpers ----


def compute_precision_recall(
    selected: Set[str],
    expected: Set[str],
) -> Dict[str, float]:
    """
    Compute precision and recall for table selection.
    """
    if not expected:
        # Recall is trivially 1.0 (nothing to retrieve).
        # Precision is 1.0 only if nothing was selected;
        # otherwise every selection is a false positive.
        p = 1.0 if not selected else 0.0
        return {"precision": p, "recall": 1.0}
    if not selected:
        return {"precision": 0.0, "recall": 0.0}
    tp = len(selected & expected)
    return {
        "precision": tp / len(selected),
        "recall": tp / len(expected),
    }


def safe_mean(values: List[float]) -> float:
    """
    Return the arithmetic mean, or 0.0 for an empty list.
    """
    return statistics.mean(values) if values else 0.0


def safe_pct(values: List[bool]) -> float:
    """
    Return the percentage of True values, or 0.0 if empty.
    """
    if not values:
        return 0.0
    return sum(values) / len(values) * 100


# ---- Orchestrator factory ----


def build_orchestrator(
    config: str,
) -> OrchestratorAgent:
    """
    Build an orchestrator for a given config.

    full        -- all agents
    no_security -- skip security
    no_refine   -- skip refinement
    no_critique -- SQL gen without critique loop
    """
    orchestrator = OrchestratorAgent()
    orchestrator.set_conversation_state(
        {"reference_date": REF_DATE}
    )

    if config != "no_refine":
        orchestrator.inject_agent(
            "refinement", QueryRefinementAgent()
        )
    if config != "no_security":
        orchestrator.inject_agent(
            "security", SecurityGovernanceAgent()
        )
    orchestrator.inject_agent(
        "schema", SchemaIntelligenceAgent()
    )
    if config == "no_critique":
        orchestrator.inject_agent(
            "sql_generation",
            NoCritiqueSQLGenAgent(),
        )
    else:
        orchestrator.inject_agent(
            "sql_generation", SQLGenerationAgent()
        )

    return orchestrator


# ---- SQL execution ----


def try_execute_sql(
    sql: Optional[str],
) -> Dict[str, Any]:
    """
    Execute SQL against the database.

    Returns execution_success, row_count, error,
    and sample_rows (first 3 rows).
    """
    if not sql:
        return {
            "execution_success": False,
            "row_count": 0,
            "error": "No SQL generated",
            "sample_rows": [],
        }
    try:
        rows = execute_query(sql)
        return {
            "execution_success": True,
            "row_count": len(rows),
            "error": None,
            "sample_rows": [
                {k: str(v) for k, v in row.items()}
                for row in rows[:3]
            ],
        }
    except Exception as e:
        return {
            "execution_success": False,
            "row_count": 0,
            "error": str(e),
            "sample_rows": [],
        }


def execute_sql_if_allowed(
    gq: Dict[str, Any],
    response: AgenticResponse,
) -> Dict[str, Any]:
    """
    Run the generated SQL only when the golden query
    expects an "allowed" outcome and SQL was produced.
    """
    should_execute = (
        gq["expected_outcome"] == "allowed"
        and response.generated_sql
    )
    if should_execute:
        return try_execute_sql(response.generated_sql)
    return {
        "execution_success": None,
        "row_count": 0,
        "error": "Skipped (blocked or no SQL)",
        "sample_rows": [],
    }


# ---- Chain serialization ----


def serialize_chain(
    chain: Optional[List[ExecutionChainStep]],
) -> List[Dict[str, Any]]:
    """
    Serialize execution chain for JSONL output.

    Preserves every field so the record is a complete
    audit trail.
    """
    steps = []
    for step in chain or []:
        if step is None:
            continue
        steps.append({
            "agent_name": step.agent_name,
            "action": step.action,
            "input_data": step.input_data,
            "output_data": step.output_data,
            "duration_ms": round(step.duration_ms, 1),
            "veto_reason": step.veto_reason,
        })
    return steps


# ---- Agent step parsers ----


def default_agent_details() -> Dict[str, Any]:
    """
    Return empty-state dicts for every agent slot.

    Used as the starting point before populating with
    actual execution chain data.
    """
    return {
        "refinement": {
            "present": False,
            "refined_query": None,
            "has_ambiguity": None,
            "duration_ms": 0,
        },
        "security": {
            "present": False,
            "blocked": False,
            "veto_reason": None,
            "risk_score": None,
            "action": None,
            "duration_ms": 0,
        },
        "schema": {
            "present": False,
            "tables_selected": [],
            "tokens_before": 0,
            "tokens_after": 0,
            "token_reduction_pct": 0,
            "entities_extracted": None,
            "fk_paths": None,
            "duration_ms": 0,
        },
        "sql_generation": {
            "present": False,
            "attempts": 0,
            "confidence": 0,
            "explanation": None,
            "critique_summary": None,
            "critique_history": None,
            "duration_ms": 0,
        },
    }


def parse_refinement_step(
    step: ExecutionChainStep,
    od: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extract refinement agent fields from a chain step.
    """
    return {
        "present": True,
        "refined_query": od.get("refined_query"),
        "has_ambiguity": od.get("has_ambiguity"),
        "duration_ms": round(step.duration_ms, 1),
    }


def parse_security_step(
    step: ExecutionChainStep,
    od: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extract security agent fields from a chain step.
    """
    result = {
        "present": True,
        "blocked": bool(step.veto_reason),
        "veto_reason": step.veto_reason,
        "risk_score": od.get("risk_score"),
        "action": step.action,
        "duration_ms": round(step.duration_ms, 1),
    }
    return result


def parse_schema_step(
    step: ExecutionChainStep,
    od: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extract schema agent fields from a chain step.
    """
    return {
        "present": True,
        "tables_selected": od.get("tables", []),
        "tokens_before": od.get("tokens_before", 0),
        "tokens_after": od.get("tokens_after", 0),
        "token_reduction_pct": od.get(
            "reduction_pct", 0
        ),
        "entities_extracted": od.get(
            "entities_extracted"
        ),
        "fk_paths": od.get("fk_paths"),
        "duration_ms": round(step.duration_ms, 1),
    }


def parse_sql_gen_step(
    step: ExecutionChainStep,
    od: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extract SQL generation agent fields from a chain step.
    """
    return {
        "present": True,
        "attempts": od.get("attempts", 0),
        "confidence": od.get("confidence", 0),
        "explanation": od.get("explanation"),
        "critique_summary": od.get("critique_summary"),
        "critique_history": od.get("critique_history"),
        "duration_ms": round(step.duration_ms, 1),
    }


def detect_security_fallback(
    security: Dict[str, Any],
    response: Optional[AgenticResponse],
) -> None:
    """
    Detect security blocks from response.error_message
    when the veto path bypassed the execution chain.
    """
    if (
        security["present"]
        or response is None
        or not response.error_message
    ):
        return
    if "Security Agent blocked" not in response.error_message:
        return
    security["present"] = True
    security["blocked"] = True
    security["veto_reason"] = response.error_message
    security["action"] = "escalated_to_human"


def extract_agent_details(
    chain: Optional[List[ExecutionChainStep]],
    response: Optional[AgenticResponse] = None,
) -> Dict[str, Any]:
    """
    Walk the execution chain and populate per-agent
    detail dicts, with a fallback for security vetoes
    that bypass the chain.
    """
    details = default_agent_details()

    for step in chain or []:
        if step is None:
            continue
        od = step.output_data or {}

        if step.agent_name == "Query Refinement":
            details["refinement"] = (
                parse_refinement_step(step, od)
            )
        elif "Security" in step.agent_name:
            details["security"] = (
                parse_security_step(step, od)
            )
        elif "Schema" in step.agent_name:
            details["schema"] = (
                parse_schema_step(step, od)
            )
        elif "SQL" in step.agent_name:
            details["sql_generation"] = (
                parse_sql_gen_step(step, od)
            )

    detect_security_fallback(
        details["security"], response
    )
    return details


# ---- Ground-truth comparison ----


def classify_outcome(
    gq: Dict[str, Any],
    agents: Dict[str, Any],
    response: AgenticResponse,
) -> str:
    """
    Determine the actual outcome category for a query.

    When the veto goes through _escalate_to_human the
    specific reason is lost, so we fall back to keyword
    matching on the NL query to distinguish PII from
    destructive blocks.
    """
    if not agents["security"]["blocked"]:
        if response.success and response.generated_sql:
            return "allowed"
        return "failed"

    veto = agents["security"]["veto_reason"] or ""
    if "PII" in veto:
        return "blocked_pii"

    destructive = re.search(
        r"\b(DELETE|DROP|UPDATE|ALTER|TRUNCATE)\b",
        gq["nl_query"],
        re.IGNORECASE,
    )
    return (
        "blocked_destructive"
        if destructive
        else "blocked_pii"
    )


def match_sql_pattern(
    gq: Dict[str, Any],
    response: AgenticResponse,
) -> Optional[bool]:
    """
    Check generated SQL against the expected pattern.

    Returns None when no pattern is defined or no SQL
    was generated.
    """
    pattern = gq.get("expected_sql_pattern")
    if not pattern or not response.generated_sql:
        return None
    return bool(
        re.search(
            pattern,
            response.generated_sql,
            re.IGNORECASE | re.DOTALL,
        )
    )


def check_outcome(
    gq: Dict[str, Any],
    response: AgenticResponse,
    agents: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare response against golden query ground truth.

    Returns outcome_match, schema precision/recall,
    and sql_pattern_match.
    """
    expected = gq["expected_outcome"]
    actual = classify_outcome(gq, agents, response)

    expected_tables = set(
        gq.get("expected_tables", [])
    )
    selected_tables = set(
        agents["schema"]["tables_selected"]
    )
    pr = compute_precision_recall(
        selected_tables, expected_tables
    )

    return {
        "expected_outcome": expected,
        "actual_outcome": actual,
        "outcome_match": actual == expected,
        "expected_tables": sorted(expected_tables),
        "selected_tables": sorted(selected_tables),
        "schema_precision": round(pr["precision"], 2),
        "schema_recall": round(pr["recall"], 2),
        "expected_sql_pattern": gq.get(
            "expected_sql_pattern"
        ),
        "sql_pattern_match": match_sql_pattern(
            gq, response
        ),
    }


# ---- Core ----


def build_jsonl_record(
    gq: Dict[str, Any],
    config: str,
    response: AgenticResponse,
    latency_ms: float,
    agents: Dict[str, Any],
    exec_result: Dict[str, Any],
    ground_truth: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Assemble the complete JSONL record for one
    (query, config) evaluation pair.
    """
    return {
        "query_id": gq["id"],
        "config": config,
        "nl_query": gq["nl_query"],
        "role": gq.get("role", "analyst"),
        "difficulty": gq.get("difficulty"),
        "failure_mode_tested": gq.get(
            "failure_mode_tested"
        ),
        "success": response.success,
        "generated_sql": response.generated_sql,
        "confidence": response.confidence_score,
        "latency_ms": round(latency_ms, 1),
        "error_message": response.error_message,
        "natural_language_summary": (
            response.natural_language_summary
        ),
        "execution_success": (
            exec_result["execution_success"]
        ),
        "row_count": exec_result["row_count"],
        "execution_error": exec_result["error"],
        "sample_rows": exec_result["sample_rows"],
        "agents": agents,
        "ground_truth": ground_truth,
        "execution_chain": serialize_chain(
            response.execution_chain
        ),
    }


async def run_query(
    orchestrator: OrchestratorAgent,
    gq: Dict[str, Any],
    config: str,
) -> Dict[str, Any]:
    """
    Run a single golden query through a config.

    Returns a complete JSONL record.
    """
    request = QueryRequest(
        natural_language=gq["nl_query"],
        user_context={
            "role": gq.get("role", "analyst"),
        },
    )

    start = time.perf_counter()
    response = await orchestrator.process_query(
        request
    )
    latency_ms = (
        (time.perf_counter() - start) * 1000
    )

    agents = extract_agent_details(
        chain=response.execution_chain,
        response=response,
    )
    exec_result = execute_sql_if_allowed(gq, response)
    ground_truth = check_outcome(
        gq, response, agents
    )

    return build_jsonl_record(
        gq, config, response, latency_ms,
        agents, exec_result, ground_truth,
    )


# ---- Ablation runner ----


def suppress_agent_logging() -> None:
    """
    Silence per-query agent logs so the ablation
    output stays readable.
    """
    for name in [
        "text_to_sql.agents.orchestrator",
        "text_to_sql.agents.query_refinement",
        "text_to_sql.agents.security_governance",
        "text_to_sql.agents.schema_intelligence",
        "text_to_sql.agents.sql_generation",
    ]:
        logging.getLogger(name).setLevel(
            logging.WARNING
        )


def init_config_stats() -> Dict[str, Dict[str, List]]:
    """
    Create empty per-config stat accumulators.
    """
    return {
        c: {
            "outcome_match": [],
            "schema_precision": [],
            "schema_recall": [],
            "confidence": [],
            "latency_ms": [],
            "security_blocked": [],
            "sql_pattern_match": [],
        }
        for c in CONFIGS
    }


def collect_record_stats(
    stats: Dict[str, List],
    record: Dict[str, Any],
) -> None:
    """
    Append one record's metrics to the running stats.
    """
    gt = record["ground_truth"]
    stats["outcome_match"].append(
        gt["outcome_match"]
    )
    stats["schema_precision"].append(
        gt["schema_precision"]
    )
    stats["schema_recall"].append(
        gt["schema_recall"]
    )
    stats["confidence"].append(record["confidence"])
    stats["latency_ms"].append(record["latency_ms"])
    stats["security_blocked"].append(
        record["agents"]["security"]["blocked"]
    )
    if gt["sql_pattern_match"] is not None:
        stats["sql_pattern_match"].append(
            gt["sql_pattern_match"]
        )


async def run_config(
    config: str,
    golden_queries: List[Dict[str, Any]],
    jsonl_file,
    stats: Dict[str, List],
    verbose: bool,
) -> None:
    """
    Run all golden queries through one config,
    writing records to jsonl_file and accumulating
    stats.
    """
    logger.info("")
    logger.info(f"  --- {config} ---")
    orch = build_orchestrator(config)

    for i, gq in enumerate(golden_queries, 1):
        qid = gq["id"]
        logger.info(
            f"  [{i}/{len(golden_queries)}]"
            f" {qid}..."
        )

        try:
            record = await run_query(
                orch, gq, config
            )
        except Exception:
            logger.exception(
                f"  FAILED {qid} / {config}"
            )
            continue

        jsonl_file.write(
            json.dumps(record, default=str) + "\n"
        )
        jsonl_file.flush()
        collect_record_stats(stats, record)
        logger.info(
            f"         "
            f"{format_status(record, verbose)}"
        )


async def run_ablation(
    verbose: bool = False,
    query_filter: Optional[str] = None,
) -> None:
    """
    Run the full ablation study.
    """
    suppress_agent_logging()

    golden_queries = filter_golden_queries(
        load_golden_queries(), query_filter
    )
    if golden_queries is None:
        return

    total = len(golden_queries) * len(CONFIGS)
    logger.info(
        f"Ablation study: {len(golden_queries)} "
        f"queries x {len(CONFIGS)} configs "
        f"= {total} runs"
    )

    EVALS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = EVALS_DIR / f"ablation_{ts}.jsonl"
    config_stats = init_config_stats()

    with open(
        jsonl_path, "w", encoding="utf-8"
    ) as jsonl_file:
        for config in CONFIGS:
            await run_config(
                config, golden_queries,
                jsonl_file,
                config_stats[config], verbose,
            )

    logger.info("")
    logger.info(f"  JSONL output: {jsonl_path}")
    logger.info("")
    print_summary(config_stats)


# ---- Console output ----


def format_status(
    record: Dict[str, Any],
    verbose: bool,
) -> str:
    """
    Format a one-line status for a query result.
    """
    gt = record["ground_truth"]
    ok = "OK" if gt["outcome_match"] else "MISS"

    parts = [
        f"outcome={ok}",
        f"P={gt['schema_precision']:.2f}",
        f"R={gt['schema_recall']:.2f}",
        f"conf={record['confidence']:.2f}",
        f"{record['latency_ms']:.0f}ms",
    ]
    if record["agents"]["security"]["blocked"]:
        parts.append("BLOCKED")
    if record.get("execution_success"):
        parts.append(
            f"{record['row_count']} rows"
        )

    line = "  ".join(parts)

    if verbose and record.get("generated_sql"):
        sql = record["generated_sql"][:120]
        line += f"\n         SQL: {sql}"

    return line


def compute_config_row(
    stats: Dict[str, List],
) -> Dict[str, float]:
    """
    Compute summary metrics for one config's stats.
    """
    return {
        "outcome_pct": safe_pct(
            stats["outcome_match"]
        ),
        "mean_p": safe_mean(
            stats["schema_precision"]
        ),
        "mean_r": safe_mean(
            stats["schema_recall"]
        ),
        "sql_pat": safe_pct(
            stats["sql_pattern_match"]
        ),
        "avg_conf": safe_mean(stats["confidence"]),
        "avg_lat": safe_mean(stats["latency_ms"]),
        "sec_blk": sum(stats["security_blocked"]),
        "n": len(stats["outcome_match"]),
    }


def print_summary(
    config_stats: Dict[str, Dict[str, List]],
) -> None:
    """
    Print the ablation comparison table.
    """
    logger.info("  Ablation Comparison Table")
    logger.info("  " + "-" * 80)
    logger.info(
        "  Config        Outcome  Mean P  Mean R"
        "  SQL Pat  Avg Conf  Avg Lat   Sec Blk"
    )
    logger.info("  " + "-" * 80)

    for config in CONFIGS:
        r = compute_config_row(
            config_stats[config]
        )
        logger.info(
            f"  {config:<14} "
            f"{r['outcome_pct']:5.1f}%  "
            f"{r['mean_p']:5.2f}   "
            f"{r['mean_r']:5.2f}   "
            f"{r['sql_pat']:5.1f}%  "
            f"{r['avg_conf']:6.2f}    "
            f"{r['avg_lat']:6.0f}ms  "
            f"{r['sec_blk']:>3}/{r['n']}"
        )

    logger.info("  " + "-" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Ablation study for agentic text-to-SQL "
            "pipeline"
        )
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show SQL preview for each query",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help=(
            "Run for a single query ID "
            "(e.g. GQ-002)"
        ),
    )
    args = parser.parse_args()

    setup_logging()
    load_dotenv()
    asyncio.run(
        run_ablation(
            verbose=args.verbose,
            query_filter=args.query,
        )
    )
