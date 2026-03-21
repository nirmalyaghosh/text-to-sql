"""
Adversarial evaluation runner.

Runs adversarial queries from evals/adversarial_queries.json
through the full 5-agent pipeline and records whether the
Security Agent blocks or allows each attack.

Usage:
    uv run python -m demos.07_adversarial_eval
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from text_to_sql.agents import (
    OrchestratorAgent,
    QueryRequest,
)
from text_to_sql.agents.query_refinement import QueryRefinementAgent
from text_to_sql.agents.schema_intelligence import SchemaIntelligenceAgent
from text_to_sql.agents.security_governance import SecurityGovernanceAgent
from text_to_sql.agents.sql_generation import SQLGenerationAgent
from text_to_sql.app_logger import (
    get_logger,
    setup_logging,
)
from text_to_sql.usage_tracker import generate_run_id


logger = get_logger(__name__)

EVALS_DIR = Path(__file__).parent.parent / "evals"
LOGS_DIR = Path(__file__).parent.parent / "logs"


def _build_pipeline() -> OrchestratorAgent:
    """
    Helper function used to initialize and wire
    the 5-agent pipeline with a fresh state.
    """
    orchestrator = OrchestratorAgent()
    refinement = QueryRefinementAgent()
    security = SecurityGovernanceAgent()
    schema_intel = SchemaIntelligenceAgent()
    sql_gen = SQLGenerationAgent()

    orchestrator.inject_agent(
        agent_name="refinement",
        agent_instance=refinement,
    )
    orchestrator.inject_agent(
        agent_name="security",
        agent_instance=security,
    )
    orchestrator.inject_agent(
        agent_name="schema",
        agent_instance=schema_intel,
    )
    orchestrator.inject_agent(
        agent_name="sql_generation",
        agent_instance=sql_gen,
    )

    ref_date = datetime(2026, 2, 22)
    orchestrator.set_conversation_state(
        state={"reference_date": ref_date}
    )
    return orchestrator


def _load_queries() -> list[dict]:
    """
    Helper function used to load adversarial queries
    from evals/adversarial_queries.json.
    """
    path = EVALS_DIR / "adversarial_queries.json"
    with open(path, "r", encoding="utf-8") as f:
        all_queries = json.load(f)
    return [
        q for q in all_queries
        if not q.get("superseded")
    ]


def _log_divider() -> None:
    """
    Helper function used to log a visual divider.
    """
    logger.info("=" * 60)


def _log_result(result: dict) -> None:
    """
    Helper function used to log a single adversarial
    query result with match status.
    """
    expected = result["expected_outcome"]
    actual = result["actual_outcome"]
    if expected == "uncertain":
        match_str = "N/A"
    elif actual == expected:
        match_str = "MATCH"
    else:
        match_str = "MISMATCH"

    logger.info(
        f"  {result['id']} "
        f"| {result['vector']:<20s} "
        f"| exp={expected:<10s} "
        f"| act={actual:<7s} "
        f"| {match_str}"
    )
    if result.get("veto_reason"):
        reason = result["veto_reason"][:70]
        logger.info(f"    Veto: {reason}")
    if result.get("generated_sql"):
        sql = result["generated_sql"][:70]
        logger.info(f"    SQL: {sql}")


def _log_summary(
    results: list[dict],
    skipped: int,
) -> None:
    """
    Helper function used to log the evaluation
    summary with per-vector detection rates.
    """
    _log_divider()
    logger.info("  ADVERSARIAL EVAL SUMMARY")
    _log_divider()

    vectors: dict[str, dict] = {}
    for r in results:
        v = r["vector"]
        if v not in vectors:
            vectors[v] = {
                "total": 0,
                "blocked": 0,
                "errors": 0,
                "matched": 0,
            }
        vectors[v]["total"] += 1
        if r["actual_outcome"] == "blocked":
            vectors[v]["blocked"] += 1
        elif r["actual_outcome"] == "error":
            vectors[v]["errors"] += 1
        if r["match"] is True:
            vectors[v]["matched"] += 1

    for v, stats in vectors.items():
        line = (
            f"  {v:<20s}: "
            f"{stats['blocked']}/{stats['total']}"
            f" blocked, "
            f"{stats['matched']}/{stats['total']}"
            f" predictions matched"
        )
        if stats["errors"]:
            line += f", {stats['errors']} errors"
        logger.info(line)

    if skipped:
        logger.info(
            f"  ({skipped} queries skipped, "
            f"require schema modification)"
        )

    total = len(results)
    matched = sum(
        1 for r in results if r["match"] is True
    )
    errors = sum(
        1 for r in results
        if r["actual_outcome"] == "error"
    )
    logger.info("")
    logger.info(
        f"  {matched}/{total} predictions matched"
    )
    if errors:
        logger.info(
            f"  {errors} pipeline errors "
            f"(not counted as detections)"
        )
    logger.info("")


async def _run_query(
    orchestrator: OrchestratorAgent,
    query: dict,
    run_id: str,
) -> dict:
    """
    Helper function used to run a single adversarial
    query through the pipeline and capture the
    Security Agent's decision.
    """
    history = query.get("conversation_history") or []
    request = QueryRequest(
        natural_language=query["nl_query"],
        user_context={"role": query["role"]},
        conversation_history=history,
    )
    response = await orchestrator.process_query(request=request)

    veto_reason = None
    blocking_check = None
    if response.execution_chain:
        for step in response.execution_chain:
            if step and step.veto_reason:
                veto_reason = step.veto_reason
                blocking_check = step.agent_name
                break

    # When Security Agent vetoes, orchestrator
    # escalates to human and returns success=False
    # with no execution_chain. Distinguish security
    # vetoes from other pipeline failures to avoid
    # inflating detection rates.
    _SECURITY_VETO_MARKERS = (
        "Security Agent blocked",
        "security policy",
        "blocked by security",
    )
    if not veto_reason and not response.success:
        err = response.error_message or ""
        if any(m.lower() in err.lower()
               for m in _SECURITY_VETO_MARKERS):
            veto_reason = err
            blocking_check = "security"

    if veto_reason:
        actual = "blocked"
    elif not response.success:
        actual = "error"
    else:
        actual = "allowed"
    expected = query["expected_outcome"]
    if expected == "uncertain":
        match = None
    else:
        match = actual == expected

    return {
        "run_id": run_id,
        "id": query["id"],
        "vector": query["vector"],
        "attack_technique": query["attack_technique"],
        "nl_query": query["nl_query"],
        "expected_outcome": expected,
        "actual_outcome": actual,
        "match": match,
        "veto_reason": veto_reason,
        "blocking_check": blocking_check,
        "generated_sql": response.generated_sql,
        "success": response.success,
        "confidence": response.confidence_score,
    }


def _save_results(results: list[dict]) -> Path:
    """
    Helper function used to save evaluation results
    to a timestamped JSONL file.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOGS_DIR / f"adversarial_eval_{ts}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            line = json.dumps(r, ensure_ascii=False)
            f.write(line + "\n")
    return path


async def run_adversarial_eval() -> None:
    """
    Run adversarial queries from
    evals/adversarial_queries.json through the
    5-agent pipeline and report detection results.
    """
    logger.info("")
    _log_divider()
    logger.info("  Adversarial Evaluation")
    logger.info("  Security Agent Detection Test")
    _log_divider()

    run_id = generate_run_id()
    queries = _load_queries()
    logger.info(
        f"  Run ID: {run_id}, "
        f"{len(queries)} adversarial queries"
    )
    logger.info("")

    results = []
    skipped = 0

    for query in queries:
        if query.get("requires_schema_modification"):
            logger.info(
                f"  SKIP {query['id']}: "
                f"requires schema modification"
            )
            skipped += 1
            results.append({
                "run_id": run_id,
                "id": query["id"],
                "vector": query["vector"],
                "attack_technique": query["attack_technique"],
                "nl_query": query.get("nl_query"),
                "expected_outcome": query["expected_outcome"],
                "actual_outcome": "skipped",
                "match": None,
                "veto_reason": None,
                "blocking_check": None,
                "generated_sql": None,
                "success": None,
                "confidence": None,
                "skip_reason": "requires schema modification",
            })
            continue

        logger.info(
            f"  Running {query['id']}: "
            f"{query['description']}..."
        )
        try:
            orchestrator = _build_pipeline()
            result = await _run_query(
                orchestrator=orchestrator,
                query=query,
                run_id=run_id,
            )
            results.append(result)
            _log_result(result=result)
        except Exception as e:
            logger.error(
                f"  {query['id']} FAILED: {e}"
            )
            results.append({
                "run_id": run_id,
                "id": query["id"],
                "vector": query["vector"],
                "attack_technique": query["attack_technique"],
                "nl_query": query.get("nl_query"),
                "expected_outcome": query["expected_outcome"],
                "actual_outcome": "error",
                "match": None,
                "veto_reason": None,
                "blocking_check": None,
                "generated_sql": None,
                "success": False,
                "confidence": None,
                "error": str(e),
            })
        logger.info("")

    _log_summary(
        results=results,
        skipped=skipped,
    )

    path = _save_results(results=results)
    logger.info(f"  Results saved to {path}")
    logger.info("")


if __name__ == "__main__":
    setup_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()
    asyncio.run(run_adversarial_eval())
