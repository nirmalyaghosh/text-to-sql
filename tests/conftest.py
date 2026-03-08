"""
Shared pytest fixtures for Text-to-SQL tests.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
)

import pytest

from text_to_sql.agents.types import QueryRequest


EVALS_DIR = (
    Path(__file__).parent.parent / "evals"
)


@pytest.fixture
def analyst_context() -> Dict[str, Any]:
    """Standard analyst user context."""
    return {
        "role": "analyst",
        "user_id": "test_user_1",
        "org_id": "test_org",
    }


@pytest.fixture
def admin_context() -> Dict[str, Any]:
    """Standard admin user context."""
    return {
        "role": "admin",
        "user_id": "admin_1",
        "org_id": "test_org",
    }


@pytest.fixture
def golden_queries() -> List[Dict[str, Any]]:
    """Load golden query dataset."""
    path = EVALS_DIR / "golden_queries.json"
    return json.loads(
        path.read_text(encoding="utf-8")
    )


@pytest.fixture
def make_request():
    """Factory for creating QueryRequest objects."""
    def _make(
        query: str,
        role: str = "analyst",
        history: List[Dict[str, str]] = None,
    ) -> QueryRequest:
        return QueryRequest(
            natural_language=query,
            user_context={
                "role": role,
                "user_id": "test_user",
                "org_id": "test_org",
            },
            conversation_history=history or [],
        )
    return _make


@pytest.fixture
def reference_date() -> datetime:
    """Fixed reference date for temporal tests."""
    return datetime(2026, 2, 22)
