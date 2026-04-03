"""
Adversarial evaluation runner.

Runs adversarial queries from evals/adversarial_queries.json
through the full 5-agent pipeline and records whether the
Security Agent blocks or allows each attack.

Features:
    - Incremental JSONL write (each result appended
      immediately, survives crashes/power loss)
    - Auto-resume (detects latest partial JSONL,
      skips completed queries; --no-resume to disable)
    - Per-query timeout (--query-timeout, default 600s)

Usage:
    uv run python -m demos.07_adversarial_eval
    uv run python -m demos.07_adversarial_eval --no-resume
    uv run python -m demos.07_adversarial_eval --query-timeout 300
"""

import argparse
import asyncio
import json
import logging
import os

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


def _append_result(
    path: Path,
    result: dict,
) -> None:
    """
    Helper function used to append a single result
    to a JSONL file.
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(result, ensure_ascii=False)
            + "\n"
        )


def _build_pipeline(
    extended_pii: bool = False,
) -> OrchestratorAgent:
    """
    Helper function used to initialize and wire
    the 5-agent pipeline with a fresh state.
    """
    orchestrator = OrchestratorAgent()
    refinement = QueryRefinementAgent()
    security = SecurityGovernanceAgent(extended_pii=extended_pii)
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


def _classify_fp(
    expected: str,
    actual: str,
) -> str:
    """
    Helper function used to classify a golden
    query result as OK, FALSE POSITIVE,
    CORRECT BLOCK, or MISSED BLOCK.
    """
    if expected == "allowed":
        if actual == "blocked":
            return "FALSE POSITIVE"
        return "OK"
    if actual == "blocked":
        return "CORRECT BLOCK"
    return "MISSED BLOCK"


def _error_result(
    run_id: str,
    query: dict,
    outcome: str,
    error: str | None = None,
) -> dict:
    """
    Helper function used to build a result dict
    for skipped, timeout, or error outcomes.
    """
    r = {
        "run_id": run_id,
        "id": query["id"],
        "vector": query["vector"],
        "attack_technique": query["attack_technique"],
        "nl_query": query.get("nl_query"),
        "expected_outcome": query["expected_outcome"],
        "actual_outcome": outcome,
        "match": None,
        "veto_reason": None,
        "blocking_check": None,
        "generated_sql": None,
        "success": None if outcome == "skipped" else False,
        "confidence": None,
    }
    if error:
        r["error"] = error
    if outcome == "skipped":
        r["skip_reason"] = "requires schema modification"
    return r


def _find_latest_partial(
    prefix: str,
    expected_count: int,
) -> tuple[Path | None, str | None, set[str]]:
    """
    Helper function used to find the latest partial
    JSONL in logs/ for auto-resume. Returns
    (path, run_id, completed_ids) or
    (None, None, set()) if no resumable file found.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    candidates = sorted(
        LOGS_DIR.glob(f"{prefix}_*.jsonl"),
        reverse=True,
    )
    for path in candidates:
        ids = set()
        run_id = None
        with open(path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                ids.add(r["id"])
                if run_id is None:
                    run_id = r.get("run_id")
        if len(ids) < expected_count:
            return path, run_id, ids
    return None, None, set()


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
    extended_pii: bool = False,
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
    # Resolve context-sensitive outcomes:
    # blocked_extended_pii means blocked only
    # when extended_pii=ON, allowed when OFF.
    if expected == "blocked_extended_pii":
        effective_expected = (
            "blocked" if extended_pii
            else "allowed"
        )
    else:
        effective_expected = expected
    if expected == "uncertain":
        match = None
    else:
        match = actual == effective_expected

    provider_ids = [
        pid
        for step in (response.execution_chain or [])
        for pid in (step.provider_ids or [])
    ]

    return {
        "run_id": run_id,
        "id": query["id"],
        "vector": query.get("vector"),
        "attack_technique": query.get("attack_technique"),
        "nl_query": query.get("nl_query"),
        "expected_outcome": expected,
        "actual_outcome": actual,
        "match": match,
        "veto_reason": veto_reason,
        "blocking_check": blocking_check,
        "generated_sql": response.generated_sql,
        "success": response.success,
        "confidence": response.confidence_score,
        "provider_ids": provider_ids,
    }


def _save_results(
    results: list[dict],
    prefix: str = "adversarial_eval",
) -> Path:
    """
    Helper function used to save evaluation results
    to a timestamped JSONL file. Used by golden FP
    check (which does not need incremental write).
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOGS_DIR / f"{prefix}_{ts}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            line = json.dumps(r, ensure_ascii=False)
            f.write(line + "\n")
    return path


async def run_adversarial_eval(
    extended_pii: bool = False,
    query_timeout: int = 600,
    no_resume: bool = False,
) -> None:
    """
    Run adversarial queries from
    evals/adversarial_queries.json through the
    5-agent pipeline and report detection results.

    Results append to JSONL after each query.
    Auto-resumes from the latest partial JSONL
    unless no_resume is True.

    Args:
        extended_pii: Enable extended PII patterns
        query_timeout: Per-query timeout in seconds
        no_resume: Force a fresh run
    """
    pii_label = "ON" if extended_pii else "OFF"
    logger.info("")
    _log_divider()
    logger.info("  Adversarial Evaluation")
    logger.info("  Security Agent Detection Test")
    logger.info(f"  extended_pii: {pii_label}")
    logger.info(
        f"  query_timeout: {query_timeout}s"
    )
    _log_divider()

    queries = _load_queries()
    completed_ids: set[str] = set()
    results_path: Path
    run_id: str

    def _fresh_path() -> Path:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = LOGS_DIR / f"adversarial_eval_{ts}.jsonl"
        if path.exists():
            raise FileExistsError(
                f"{path} already exists. "
                f"Delete it or use --no-resume."
            )
        return path

    if not no_resume:
        rpath, rid, cids = _find_latest_partial(
            prefix="adversarial_eval",
            expected_count=len(queries),
        )
        if rpath and rid and cids:
            results_path = rpath
            run_id = rid
            completed_ids = cids
            logger.info(
                f"  Resuming run {run_id} "
                f"from {results_path.name} "
                f"({len(completed_ids)} done)"
            )
        else:
            run_id = generate_run_id()
            results_path = _fresh_path()
    else:
        run_id = generate_run_id()
        results_path = _fresh_path()

    os.environ["OPENROUTER_RUN_TAG"] = f"txt2sql-adv-{run_id}"

    logger.info(
        f"  Run ID: {run_id}, "
        f"{len(queries)} adversarial queries"
    )
    logger.info(f"  Output: {results_path}")
    logger.info("")

    all_results = []
    skipped = 0

    for query in queries:
        qid = query["id"]

        if qid in completed_ids:
            continue

        if query.get("requires_schema_modification"):
            logger.info(
                f"  SKIP {qid}: "
                f"requires schema modification"
            )
            skipped += 1
            result = _error_result(
                run_id=run_id,
                query=query,
                outcome="skipped",
            )
            _append_result(
                path=results_path, result=result,
            )
            all_results.append(result)
            continue

        logger.info(
            f"  Running {qid}: "
            f"{query['description']}..."
        )
        try:
            orchestrator = _build_pipeline(
                extended_pii=extended_pii,
            )
            result = await asyncio.wait_for(
                _run_query(
                    orchestrator=orchestrator,
                    query=query,
                    run_id=run_id,
                    extended_pii=extended_pii,
                ),
                timeout=query_timeout,
            )
            _log_result(result=result)
        except asyncio.TimeoutError:
            logger.warning(
                f"  {qid} TIMEOUT "
                f"after {query_timeout}s"
            )
            result = _error_result(
                run_id=run_id,
                query=query,
                outcome="timeout",
                error=f"timeout after {query_timeout}s",
            )
        except Exception as e:
            logger.error(f"  {qid} FAILED: {e}")
            result = _error_result(
                run_id=run_id,
                query=query,
                outcome="error",
                error=str(e),
            )
        _append_result(
            path=results_path, result=result,
        )
        all_results.append(result)
        logger.info("")

    _log_summary(
        results=all_results,
        skipped=skipped,
    )
    logger.info(f"  Results saved to {results_path}")
    logger.info("")


async def run_golden_fp_check(
    extended_pii: bool = False,
) -> None:
    """
    Run golden queries through the pipeline
    to measure false positive rate. Queries
    with expected_outcome="allowed" that get
    blocked are false positives.
    """
    pii_label = "ON" if extended_pii else "OFF"
    logger.info("")
    _log_divider()
    logger.info("  Golden Query FP Check")
    logger.info(f"  extended_pii: {pii_label}")
    _log_divider()

    run_id = generate_run_id()
    path = EVALS_DIR / "golden_queries.json"
    with open(path, "r", encoding="utf-8") as f:
        golden = json.load(f)

    logger.info(
        f"  Run ID: {run_id}, "
        f"{len(golden)} golden queries"
    )
    logger.info("")

    results = []
    for gq in golden:
        logger.info(
            f"  Running {gq['id']}: "
            f"{gq['nl_query'][:50]}..."
        )
        try:
            orchestrator = _build_pipeline(
                extended_pii=extended_pii,
            )
            result = await _run_query(
                orchestrator=orchestrator,
                query=gq,
                run_id=run_id,
                extended_pii=extended_pii,
            )
            fp_label = _classify_fp(
                expected=gq["expected_outcome"],
                actual=result["actual_outcome"],
            )
            result["fp_label"] = fp_label

            logger.info(
                f"  {gq['id']}"
                f" | exp="
                f"{gq['expected_outcome']:<18s}"
                f" | act="
                f"{result['actual_outcome']:<7s}"
                f" | {fp_label}"
            )
            if result.get("veto_reason"):
                logger.info(
                    f"    Veto:"
                    f" {result['veto_reason'][:70]}"
                )
            results.append(result)

        except Exception as e:
            logger.error(
                f"  {gq['id']} FAILED: {e}"
            )
            results.append({
                "run_id": run_id,
                "id": gq["id"],
                "nl_query": gq["nl_query"],
                "expected_outcome": (
                    gq["expected_outcome"]
                ),
                "actual_outcome": "error",
                "fp_label": "ERROR",
                "error": str(e),
            })
        logger.info("")

    # Summary
    _log_divider()
    logger.info(
        "  GOLDEN QUERY FP CHECK SUMMARY"
    )
    _log_divider()
    allowed_count = sum(
        1 for gq in golden
        if gq["expected_outcome"] == "allowed"
    )
    fp = sum(
        1 for r in results
        if r.get("fp_label") == "FALSE POSITIVE"
    )
    logger.info(
        f"  Legitimate queries:"
        f" {allowed_count}"
    )
    logger.info(
        f"  False positives: {fp}"
    )
    if allowed_count > 0:
        logger.info(
            f"  FP rate:"
            f" {fp / allowed_count:.1%}"
            f" ({fp}/{allowed_count})"
        )
    logger.info("")

    out = _save_results(
        results=results,
        prefix="golden_fp_check",
    )
    logger.info(f"  Results saved to {out}")
    logger.info("")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--extended-pii",
        action="store_true",
        help="Enable extended PII patterns",
    )
    parser.add_argument(
        "--golden-fp",
        action="store_true",
        help=(
            "Run golden query FP check "
            "instead of adversarial eval"
        ),
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Force a fresh run (skip auto-resume)",
    )
    parser.add_argument(
        "--query-timeout",
        type=int,
        default=600,
        help="Per-query timeout in seconds (default 600)",
    )
    args = parser.parse_args()

    setup_logging()
    logging.getLogger("httpx").setLevel(
        logging.WARNING
    )
    load_dotenv()

    if args.golden_fp:
        asyncio.run(
            run_golden_fp_check(
                extended_pii=args.extended_pii,
            )
        )
    else:
        asyncio.run(
            run_adversarial_eval(
                extended_pii=args.extended_pii,
                no_resume=args.no_resume,
                query_timeout=args.query_timeout,
            )
        )
