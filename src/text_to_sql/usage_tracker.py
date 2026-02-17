"""
LLM usage tracker.

Logs each LLM call (prompt preview, token usage, model, cost)
to a JSONL file for auditability and cost tracking.
"""

import json
import os
import uuid

from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from text_to_sql.app_logger import get_logger


logger = get_logger(__name__)

PROMPT_PREVIEW_LENGTH = 200

_run_id: str | None = None
_request_counter: int = 0


def _get_jsonl_handler() -> TimedRotatingFileHandler:
    """
    Create a TimedRotatingFileHandler for the JSONL usage log.
    """
    log_dir = os.getenv("LOG_FILES_DIR_PATH", "logs")
    jsonl_file = os.getenv("USAGE_LOG_FILE_NAME", "token_usage.jsonl")

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    jsonl_path = Path(log_dir) / jsonl_file

    handler = TimedRotatingFileHandler(
        filename=str(jsonl_path),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    return handler


_handler = None


def _ensure_handler() -> TimedRotatingFileHandler:
    global _handler
    if _handler is None:
        _handler = _get_jsonl_handler()
    return _handler


def generate_run_id() -> str:
    """
    Generate a new run_id and reset the request counter.
    Call this once at the start of each demo/session.
    """
    global _run_id, _request_counter
    _run_id = str(uuid.uuid4())[:8]
    _request_counter = 0
    return _run_id


def log_llm_request(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    question: str,
) -> str:
    """
    Log an LLM request with prompt previews.
    Returns a request_id (run_id + sequence number) that links
    this request to its response.
    """
    global _request_counter
    if _run_id is None:
        generate_run_id()
    _request_counter += 1
    request_id = f"{_run_id}-{_request_counter:03d}"
    entry = {
        "event": "llm_request",
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "question": question,
        "system_prompt_preview": system_prompt[:PROMPT_PREVIEW_LENGTH],
        "user_prompt_preview": user_prompt[:PROMPT_PREVIEW_LENGTH],
        "user_prompt_length": len(user_prompt),
    }
    _write_entry(entry)
    return request_id


def log_llm_response(
    *,
    request_id: str,
    model: str,
    question: str,
    usage: dict,
    generated_sql: str,
    trim_sql_preview: bool = False,
) -> None:
    """
    Log an LLM response with token usage.
    """
    generated_sql_preview = generated_sql
    if trim_sql_preview:
        if len(generated_sql) > PROMPT_PREVIEW_LENGTH:
            generated_sql_preview =\
                generated_sql[:PROMPT_PREVIEW_LENGTH] + "..."

    entry = {
        "event": "llm_response",
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "question": question,
        "generated_sql_preview": generated_sql_preview,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }
    _write_entry(entry)


def _write_entry(entry: dict) -> None:
    """
    Write a single JSON entry to the JSONL log file.
    """
    handler = _ensure_handler()
    line = json.dumps(entry, default=str)
    # Write directly to the handler's stream
    handler.stream.write(line + "\n")
    handler.stream.flush()
