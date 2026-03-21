# Text-to-SQL: From Naïve to Agentic

A progressive exploration of Text-to-SQL approaches on an enterprise-grade [schema](#schema) (35 tables, 7 domains).

This repository supports the following blog posts in the multi-part blog series.

1. [**The Naïve Way**](https://www.nirmalya.net/posts/2026/02/text-to-sql-naive-way/) - Why prompt-and-pray fails on enterprise data
2. **Schema Pruning** - FK-graph traversal to minimize token waste ([details](#schema-pruning))
3. **Agentic Text-to-SQL** - Multi-agent system with security governance ([details](#agentic-text-to-sql))
4. **Red-Teaming the Security Agent** - Crescendo-style multi-turn jailbreak detection *(coming soon)*

## Setup

```bash
# 1. Clone
git clone <repo-url>
cd text-to-sql

# 2. Create virtual environment and install

# Option A: using uv (recommended)
uv venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate       # Windows
uv pip install -e ".[dev]"

# Option B: using pip
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate       # Windows
pip install -e ".[dev]"

# 3. Configure environment
cp env.example .env
# Edit .env with your Neon DATABASE_URL and LLM API key

# 4. Initialize database
uv run python -c "from text_to_sql.db import init_db; init_db()"

# 5. Run the naïve demo
uv run python demos/01_naive_demo.py
```

## Database

Uses [Neon](https://neon.tech) serverless PostgreSQL (free tier). You could equally use Google Cloud SQL, AWS RDS, or Azure Database for PostgreSQL - only the connection string changes.

## Schema

35 tables across 7 domains simulating a multinational manufacturing and e-commerce company:

- **Manufacturing** (8 tables): products, variants, suppliers, BOMs, production runs, quality
- **Inventory** (7 tables): finished goods, raw materials, transactions, safety stock, valuation
- **Logistics** (5 tables): warehouses, shipping routes, delivery partners, shipments, customs
- **E-commerce** (4 tables): customers, orders, order items, returns
- **Analytics** (5 tables): sessions, campaigns, funnels, CLV, demand forecasts
- **Finance** (4 tables): transactions, invoices, cost allocations, profitability
- **HR** (2 tables): employees, departments

The full 35-table DDL is approximately **8,348 tokens**. Even after stripping comments, DROP statements, and operational commands (**5,164 tokens**), sending all 35 tables on every LLM call is wasteful. See [Schema Pruning](#schema-pruning) for how this is addressed.

> **Note:** [Part 1](https://www.nirmalya.net/posts/2026/02/text-to-sql-naive-way/) reported 8,414 / 5,230 tokens - those were measured during drafting before minor DDL edits (schema naming) in the final commit. The figures above are reproducible from the committed schema.

```python
import tiktoken
from pathlib import Path
from text_to_sql.schema_pruner import _extract_create_blocks

ddl = Path("schema/schema_setup.sql").read_text()
enc = tiktoken.get_encoding("o200k_base")
print(len(enc.encode(ddl)))                        # 8348 (full DDL)
print(len(enc.encode(_extract_create_blocks(ddl)))) # 5164 (CREATE TABLE blocks)
```

You can also reproduce the full token waste analysis from Part 1:
```bash
uv run python demos/02_token_waste_analysis.py
```

## Schema Pruning

Given a natural language query, the pruner identifies the minimal set of tables needed - without calling an LLM. It works in three stages:

1. **Entity resolution** - maps query terms to tables via direct name matching, business-term synonyms, and column-name lookup
2. **FK-graph traversal** - BFS from seed tables through foreign key edges to include join paths
3. **DDL extraction** - emits only the selected `CREATE TABLE` blocks, with token counts before and after

The result is deterministic and fully reproducible.

```bash
# Run tests
uv run pytest tests/test_schema_pruner.py -v

# Run benchmark (all golden queries)
uv run python demos/05_schema_pruning_benchmark.py

# Verbose output or single query
uv run python demos/05_schema_pruning_benchmark.py --verbose
uv run python demos/05_schema_pruning_benchmark.py --query GQ-002

# Ablation study (contribution of each resolver layer)
uv run python demos/05_schema_pruning_ablation_study.py
uv run python demos/05_schema_pruning_ablation_study.py --verbose

# Approach comparison chart (pruner vs DAIL-SQL, RESDSQL, DIN-SQL, C3SQL)
uv run python demos/05_schema_pruning_approach_comparison.py
```

No database connection or API keys needed - the pruner works entirely from DDL text.

### End-to-end validation

Compares full-schema vs pruned-schema SQL generation: for each golden query, generates SQL via the LLM with both the full and pruned schemas, executes both against the database, and classifies the outcome. Requires `OPENAI_API_KEY` and `DATABASE_URL` in `.env`.

```bash
uv run python demos/05_schema_pruning_e2e_validation.py
uv run python demos/05_schema_pruning_e2e_validation.py --verbose
uv run python demos/05_schema_pruning_e2e_validation.py --query GQ-002
```

```python
from text_to_sql.schema_pruner import prune_for_query

result = prune_for_query("How many orders were placed last month?")
print(result.selected_tables)   # ['orders']
print(result.reduction_pct)     # 97.0
print(f"{result.full_schema_tokens} -> {result.pruned_schema_tokens} tokens")
```

Link to [blog post](https://www.nirmalya.net/posts/2026/02/text-to-sql-schema-pruning/).

## Agentic Text-to-SQL

Five specialised agents, built on [Pydantic AI](https://ai.pydantic.dev/), collaborate through an orchestrator to convert natural language to SQL:

| Agent | Responsibility |
|---|---|
| **Orchestrator** | Sequences the pipeline, collects execution chain for provenance |
| **Query Refinement** | Temporal resolution, pronoun/entity mapping, ambiguity detection |
| **Security & Governance** | RBAC, PII detection, read-only enforcement, risk scoring (veto power) |
| **Schema Intelligence** | Entity extraction via LLM, FK-graph BFS for join paths, DDL pruning |
| **SQL Generation** | LLM-based generation with a self-critique loop (up to 3 attempts) |

Key design choices:

- **Fail-closed security**: the Security agent can veto any query; critique failures default to invalid (retry, not pass-through)
- **Self-critique loop**: a separate critique agent reviews generated SQL for correctness before accepting it; corrections are syntax-validated before use
- **Provenance tracking**: every agent records an `ExecutionChainStep` so the full decision trail is inspectable
- **Cross-turn context**: conversation history flows through the pipeline for multi-turn queries

```bash
# Core demo (Refinement + Security + Orchestrator)
uv run python -m demos.06_agentic_core

# Full pipeline (all 5 agents end-to-end)
uv run python -m demos.06_agentic_full_pipeline

# Ablation study (measure each agent's contribution)
uv run python -m demos.06_agentic_ablation_study
uv run python -m demos.06_agentic_ablation_study --verbose
uv run python -m demos.06_agentic_ablation_study --query GQ-002
```

Requires `OPENAI_API_KEY` and `DATABASE_URL` in `.env`.

### LLM Configuration

Endpoint definitions (provider, model, API key env var, pricing) live in `llm_endpoints.yaml`. The config loader at `src/text_to_sql/llm_config.py` validates and resolves them:

```python
from text_to_sql.llm_config import get_client, get_model_name

client = get_client("openai-gpt4o-mini")
model = get_model_name("openai-gpt4o-mini")
```

See `env.example` for required API key variables.

### Observability

Every LLM call across the entire codebase (naive demos, schema pruning e2e, and the agentic pipeline) is logged to `logs/token_usage.jsonl`. Each entry records the model, prompt preview, and token counts (input/output). Entries are linked by `request_id` within a `run_id`.

End-to-end validation outcomes (row counts, pattern match, schema reduction) are logged separately to `logs/e2e_validation_results.jsonl`. The `run_id` field links entries across both files for cost-per-query analysis.

```bash
# Tail recent token usage
tail -5 logs/token_usage.jsonl | python -m json.tool
```

### Tests

98 unit tests cover deterministic logic (no LLM calls needed):

```bash
uv run pytest tests/ -v
```
