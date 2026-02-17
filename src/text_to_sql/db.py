"""
Database connection and query execution for Neon PostgreSQL.
"""

import os
import re

import psycopg2
import psycopg2.extras

from pathlib import Path

from dotenv import load_dotenv

from text_to_sql.app_logger import get_logger


load_dotenv()

logger = get_logger(__name__)

SCHEMA_DIR = Path(__file__).parent.parent.parent / "schema"


def execute_query(sql: str) -> list[dict]:
    """
    Helper function used to execute a SQL query and return results
    as a list of dicts.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            conn.commit()
            return []
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_connection():
    """
    Helper function used to connect to a PostgreSQL database
    using `DATABASE_URL` specified in the `.env`.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set in .env")
    conn = psycopg2.connect(database_url)
    with conn.cursor() as cur:
        cur.execute("SET search_path TO mfg_ecommerce, public")
    return conn


def get_schema_ddl(llm_context: bool = True) -> str:
    """
    Helper function used to read the schema DDL file as a string.

    When llm_context=True (default), returns only the CREATE TABLE
    blocks — stripping comments, DROP statements, and operational
    commands that waste tokens and add no structural information.

    When llm_context=False, returns the full file as-is
    (used by init_db to set up the database).
    """
    schema_file = SCHEMA_DIR / "schema_setup.sql"
    schema_sql = schema_file.read_text(encoding="utf-8")

    if not llm_context:
        return schema_sql

    blocks = re.findall(
        r"(CREATE TABLE\b.*?\);)",
        schema_sql,
        re.DOTALL,
    )
    return "\n\n".join(blocks)


def init_db():
    """
    Helper function used to initialize the database: create tables
    and load sample data.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Create schema
            schema_sql = get_schema_ddl(llm_context=False)
            cur.execute(schema_sql)

            # Load sample data
            data_sql = (SCHEMA_DIR / "sample_data.sql")\
                .read_text(encoding="utf-8")
            cur.execute(data_sql)

        conn.commit()
        logger.info("DB initialized: schema created and sample data loaded.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    from text_to_sql.app_logger import setup_logging
    setup_logging()
    init_db()
