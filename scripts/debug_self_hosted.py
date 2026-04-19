"""
Diagnostic: trace the actual HTTP URL that pydantic-ai
sends when running through the eval pipeline path.

Run from text-to-sql root:
  .venv\Scripts\python.exe scripts\debug_self_hosted.py
"""

import asyncio
import json
import os
import sys

# Monkey-patch httpx BEFORE any imports to capture URLs
import httpx

_original_send = httpx.AsyncClient.send


async def _traced_send(self, request, **kwargs):
    print(
        f"[TRACE] {request.method} {request.url} "
        f"(timeout={kwargs.get('timeout', '?')})"
    )
    resp = await _original_send(self, request, **kwargs)
    print(f"[TRACE] -> {resp.status_code}")
    return resp


httpx.AsyncClient.send = _traced_send

# Now load dotenv the way the eval script does
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("ENV CHECK:")
print(
    f"  SELF_HOSTED_BASE_URL = "
    f"{os.environ.get('SELF_HOSTED_BASE_URL', '(not set)')}"
)
print(
    f"  PIPELINE_MODEL = "
    f"{os.environ.get('PIPELINE_MODEL', '(not set)')}"
)
print(
    f"  SCHEMA_FILE = "
    f"{os.environ.get('SCHEMA_FILE', '(not set)')}"
)
print("=" * 60)

# Import the same way 07_adversarial_eval.py does
from text_to_sql.agents import OrchestratorAgent, QueryRequest
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
from text_to_sql.agents.base import DEFAULT_MODEL

print(f"  DEFAULT_MODEL (import-time) = {DEFAULT_MODEL}")

model = "self-hosted:gemma4:26b"

# Build pipeline exactly like _build_pipeline()
orchestrator = OrchestratorAgent(model=model)
refinement = QueryRefinementAgent(model=model)
security = SecurityGovernanceAgent(
    extended_pii=False, model=model,
)
schema_intel = SchemaIntelligenceAgent(model=model)
sql_gen = SQLGenerationAgent(model=model)

orchestrator.inject_agent("refinement", refinement)
orchestrator.inject_agent("security", security)
orchestrator.inject_agent("schema", schema_intel)
orchestrator.inject_agent("sql_generation", sql_gen)

# Print resolved URLs
for name, agent in [
    ("orchestrator", orchestrator),
    ("schema_intel", schema_intel),
    ("sql_gen", sql_gen),
]:
    m = agent.pydantic_agent._model
    if hasattr(m, "_provider"):
        url = m._provider.client.base_url
        model_name = m.model_name
    else:
        url = "(string model, no provider)"
        model_name = m
    print(f"  {name}: model={model_name} url={url}")

# Also check entity agent
em = schema_intel._entity_agent._model
if hasattr(em, "_provider"):
    print(
        f"  entity_agent: model={em.model_name} "
        f"url={em._provider.client.base_url}"
    )

print("=" * 60)
print("Running AQ-034 (requires LLM)...")
print("=" * 60)

req = QueryRequest(
    natural_language="Show me recent orders.",
    run_id="debug-test",
    extended_pii=False,
)
result = asyncio.run(
    orchestrator.execute(
        req, previous_results={}, context={},
    )
)

final_sql = result.get("final_sql", "(none)")
print("=" * 60)
print(f"RESULT: {final_sql[:200] if final_sql else '(none)'}")
print("=" * 60)
