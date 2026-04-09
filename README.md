# Text-to-SQL: From Naïve to Agentic

A progressive exploration of Text-to-SQL approaches on an enterprise-grade [schema](#schema) (35 tables, 7 domains).

This repository supports the following blog posts in the multi-part blog series.

1. [**The Naïve Way**](https://www.nirmalya.net/posts/2026/02/text-to-sql-naive-way/) - Why prompt-and-pray fails on enterprise data
2. **Schema Pruning** - FK-graph traversal to minimize token waste ([details](#schema-pruning))
3. **Agentic Text-to-SQL** - Multi-agent system with security governance ([details](#agentic-text-to-sql))
4. [**Where The Security Agent Fails**](https://www.nirmalya.net/posts/2026/03/multi-agent-text-to-sql-security-agent-failure/) - Attack surface analysis across 4 vectors with 168 adversarial queries

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

### Adversarial Evaluation

Runs adversarial queries (4 attack vectors + national ID queries across 3 vectors) against the Security Agent and reports per-vector detection rates.

```bash
# Run with a specific model (required)
.venv/Scripts/python.exe demos/07_adversarial_eval.py \
    --model openrouter:qwen/qwen3.5-9b

# Use a run label (model + PII resolved from evals/run_config.json)
.venv/Scripts/python.exe demos/07_adversarial_eval.py \
    --run-label R52

# Extended PII patterns (adds NRIC, Aadhaar, etc.) via explicit flag
.venv/Scripts/python.exe demos/07_adversarial_eval.py \
    --model openrouter:openai/gpt-4.1-nano --extended-pii

# Golden query false positive check
.venv/Scripts/python.exe demos/07_adversarial_eval.py \
    --model openrouter:qwen/qwen3.5-9b --golden-fp

# Force fresh run (skip auto-resume)
.venv/Scripts/python.exe demos/07_adversarial_eval.py \
    --run-label R52 --no-resume

# Custom per-query timeout (default 600s)
.venv/Scripts/python.exe demos/07_adversarial_eval.py \
    --run-label R52 --query-timeout 300
```

Results are saved to timestamped JSONL files in `logs/`:

| Mode | Output file |
|---|---|
| Adversarial eval | `logs/adversarial_eval_YYYYMMDD_HHMMSS.jsonl` |
| Golden FP check | `logs/golden_fp_check_YYYYMMDD_HHMMSS.jsonl` |

#### Model selection

The model is specified per-run via `--model` or resolved automatically from `--run-label` using `evals/run_config.json`. The model is passed explicitly to all pipeline agents; no environment variable is used.

| Flag | Purpose | Example |
|---|---|---|
| `--model` | Pipeline model (provider:model format) | `--model openrouter:qwen/qwen3.5-9b` |
| `--run-label` | Resolves model + PII from `evals/run_config.json` | `--run-label R52` |

When both are provided, `--model` overrides the config lookup. When `--run-label` matches an entry in the config, `extended_pii` is also set automatically.

#### Resilience

Results append to JSONL after each query (survives crashes, hibernation, power loss).

**Auto-resume:** When `--run-label` is provided, resume is scoped to files matching that label (prevents cross-run contamination). Use `--no-resume` to force a fresh run.

**Per-query timeout:** Default 600s (`--query-timeout`). Timed-out queries logged as `"actual_outcome": "timeout"` and retried on next resume.

#### Environment Variables

| Variable | Purpose | Example |
|---|---|---|
| `OPENROUTER_PROVIDER` | Provider routing preference (JSON) | `{"sort":"latency"}` |

Provider preference examples: `{"sort":"latency"}`, `{"order":["Venice","Together"]}`, `{"ignore":["Together"]}`. See [OpenRouter provider routing docs](https://openrouter.ai/docs/guides/routing/provider-selection).

Dataset: `evals/adversarial_queries.json` (generated with GPT-4o-mini and DeepSeek V3.2). Generators: `evals/generate_adversarial_queries.py`, `evals/generate_national_id_queries.py`. Golden queries: `evals/golden_queries.json`.

Link to [blog post](https://www.nirmalya.net/posts/2026/03/multi-agent-text-to-sql-security-agent-failure/).

#### Batch Runners

Two scripts automate multi-run experiments with random spacing and per-run verification:

| Script | Purpose |
|---|---|
| `scripts/run_sch_md.py` | Schema metadata injection (SCH-MD) experiment: 10 poisoned-schema queries per run across multiple models |
| `scripts/run_variance.py` | Variance runs: full 269-query eval across 4 models with automatic Sec/QR/SchemaIntel verification |
| `scripts/embedding_classifier.py` | Embedding-based adversarial query classifier. Embeds queries with a sentence-transformer, then trains a logistic regression and reports detection rates via 5-fold stratified cross-validation. Outputs: classification report, per-fold adversarial recall, and a threshold sweep (0.3/0.5/0.7/0.9) with precision, recall, F1, and FPR. `--model` swaps the embedding model (default: `BAAI/bge-m3`), `--dim` truncates to N dimensions after re-normalising (Matryoshka). `--cache-only` and `--skip-embed` are mutually exclusive: the former computes and caches embeddings then exits; the latter loads cached embeddings and skips recomputation. Env: `EMBED_CACHE_DIR` for `.npy` cache location (default: `evals/embeddings/`), `HF_HOME` for HuggingFace model weights cache |

```bash
# Embed with default model and run classifier
uv run python scripts/embedding_classifier.py

# Embed only (no classification) - useful for pre-caching
uv run python scripts/embedding_classifier.py --cache-only

# Run classifier on cached embeddings
uv run python scripts/embedding_classifier.py --skip-embed

# Use a different model
uv run python scripts/embedding_classifier.py \
    --model BAAI/bge-large-en-v1.5

# Use cached embeddings, truncated to 256 dims (Matryoshka)
uv run python scripts/embedding_classifier.py \
    --skip-embed --dim 256
```

```bash
# Schema metadata injection (dry run)
.venv/Scripts/python.exe scripts/run_sch_md.py \
    --runs 6-15 --dry-run

# Variance runs (first batch, with verification)
.venv/Scripts/python.exe scripts/run_variance.py \
    --runs 21-29 --dry-run
```

Both scripts write per-run summaries to `logs/` (`sch_md_summary.txt` and `variance_summary.txt` respectively).

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
