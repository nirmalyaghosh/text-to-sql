# Text-to-SQL: From Naïve to Agentic

A progressive exploration of Text-to-SQL approaches on an enterprise-grade schema (35 tables, 7 domains).

## Blog Series

1. **The Naïve Way** — Why prompt-and-pray fails on enterprise data
2. **Agentic Text-to-SQL** — 8 specialized agents with security governance *(coming soon)*
3. **Red-Teaming the Security Agent** — Crescendo-style multi-turn jailbreak detection *(coming soon)*

## Setup

```bash
# 1. Clone and install
git clone <repo-url>
cd text-to-sql
pip install -e ".[dev]"

# 2. Configure environment
cp .env.example .env
# Edit .env with your Neon DATABASE_URL and LLM API key

# 3. Initialize database
python -c "from text_to_sql.db import init_db; init_db()"

# 4. Run the naïve demo
python demos/01_naive_demo.py
```

## Database

Uses [Neon](https://neon.tech) serverless PostgreSQL (free tier). You could equally use Google Cloud SQL, AWS RDS, or Azure Database for PostgreSQL — only the connection string changes.

## Schema

35 tables across 7 domains simulating a multinational manufacturing and e-commerce company:

- **Manufacturing** (8 tables): products, variants, suppliers, BOMs, production runs, quality
- **Inventory** (7 tables): finished goods, raw materials, transactions, safety stock, valuation
- **Logistics** (5 tables): warehouses, shipping routes, delivery partners, shipments, customs
- **E-commerce** (4 tables): customers, orders, order items, returns
- **Analytics** (5 tables): sessions, campaigns, funnels, CLV, demand forecasts
- **Finance** (4 tables): transactions, invoices, cost allocations, profitability
- **HR** (2 tables): employees, departments
