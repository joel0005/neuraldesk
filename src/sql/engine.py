"""Text-to-SQL Engine — converts natural language questions into SQL queries."""

import os
import re
import json
import sqlite3


# Only these SQL statements are allowed. Everything else is blocked.
ALLOWED_PREFIXES = ("select", "with")
BLOCKED_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "replace", "attach", "detach", "pragma", "vacuum", "reindex",
]


class SQLEngine:
    """Reads a SQLite file, extracts schema, generates SQL from questions, runs it safely."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ---------- Schema extraction ----------

    def extract_schema(self, sample_rows: int = 3) -> dict:
        """Read table names, columns, types, and a few sample rows."""
        if not os.path.exists(self.db_path):
            return {"error": f"Database file not found: {self.db_path}"}

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            tables = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()

            schema = {"tables": []}

            for t in tables:
                table_name = t["name"]
                cols = cur.execute(f'PRAGMA table_info("{table_name}")').fetchall()
                columns = [{"name": c["name"], "type": c["type"] or "TEXT"} for c in cols]

                samples = []
                try:
                    rows = cur.execute(f'SELECT * FROM "{table_name}" LIMIT {sample_rows}').fetchall()
                    samples = [dict(r) for r in rows]
                except Exception:
                    samples = []

                try:
                    count = cur.execute(f'SELECT COUNT(*) AS c FROM "{table_name}"').fetchone()["c"]
                except Exception:
                    count = 0

                schema["tables"].append({
                    "name": table_name,
                    "columns": columns,
                    "row_count": count,
                    "samples": samples,
                })

            conn.close()
            return schema

        except Exception as e:
            return {"error": str(e)}

    # ---------- Schema formatting for the LLM ----------

    @staticmethod
    def schema_to_prompt(schema: dict) -> str:
        """Turn the schema dict into readable text for the LLM."""
        if not schema or "tables" not in schema:
            return "No schema available."

        parts = []
        for t in schema["tables"]:
            cols = ", ".join(f'{c["name"]} ({c["type"]})' for c in t["columns"])
            parts.append(f'TABLE "{t["name"]}" ({t.get("row_count", 0)} rows)\n  Columns: {cols}')

            if t.get("samples"):
                sample = t["samples"][0]
                sample_txt = ", ".join(f"{k}={v}" for k, v in list(sample.items())[:8])
                parts.append(f"  Example row: {sample_txt}")

        return "\n\n".join(parts)

    # ---------- Safety ----------

    @staticmethod
    def is_safe(sql: str) -> tuple:
        """Return (ok, reason). Only read-only single statements allowed."""
        if not sql or not sql.strip():
            return False, "Empty query"

        cleaned = sql.strip().rstrip(";").strip()
        lowered = cleaned.lower()

        if not lowered.startswith(ALLOWED_PREFIXES):
            return False, "Only SELECT queries are allowed"

        # Block multiple statements
        if ";" in cleaned:
            return False, "Multiple statements are not allowed"

        # Block dangerous keywords appearing as whole words
        for kw in BLOCKED_KEYWORDS:
            if re.search(rf"\b{kw}\b", lowered):
                return False, f"Blocked keyword: {kw}"

        return True, ""

    # ---------- SQL generation ----------

    def generate_sql(self, question: str, schema: dict, llm_router, bot: dict) -> dict:
        """Ask the LLM to write a SQL query for this question."""
        from ..llm.base import LLMMessage

        schema_text = self.schema_to_prompt(schema)

        system = (
            "You are a SQL expert. Write ONE SQLite SELECT query that answers the user's question.\n\n"
            f"DATABASE SCHEMA:\n{schema_text}\n\n"
            "RULES:\n"
            "- Return ONLY the SQL query. No explanation, no markdown, no code blocks.\n"
            "- Use ONLY tables and columns that exist in the schema above.\n"
            "- Only SELECT queries. Never INSERT, UPDATE, DELETE, or DROP.\n"
            "- Always add LIMIT 100 unless the question asks for a count or aggregate.\n"
            "- Quote table and column names with double quotes.\n"
            "- If the question cannot be answered from this schema, return exactly: NO_QUERY"
        )

        try:
            response = llm_router.generate(
                messages=[
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=question),
                ],
                provider=bot.get("llm_provider") or "ollama",
                model=bot.get("llm_model") or "gemma3:latest",
                temperature=0.0,
                max_tokens=500,
                api_key=bot.get("llm_api_key") or "",
            )
        except Exception as e:
            return {"success": False, "error": f"LLM error: {e}"}

        sql = (response.content or "").strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()

        if "NO_QUERY" in sql.upper():
            return {"success": False, "error": "NO_QUERY"}

        ok, reason = self.is_safe(sql)
        if not ok:
            return {"success": False, "error": f"Unsafe query rejected: {reason}"}

        return {"success": True, "sql": sql}

    # ---------- Execution ----------

    def run_query(self, sql: str, max_rows: int = 100) -> dict:
        """Run a validated SELECT query and return rows."""
        ok, reason = self.is_safe(sql)
        if not ok:
            return {"success": False, "error": reason}

        if not os.path.exists(self.db_path):
            return {"success": False, "error": "Database file not found"}

        try:
            # Read-only connection
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchmany(max_rows)
            columns = [d[0] for d in cur.description] if cur.description else []
            result = [dict(r) for r in rows]
            conn.close()

            return {"success": True, "columns": columns, "rows": result, "row_count": len(result)}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ---------- Result formatting ----------

    @staticmethod
    def rows_to_text(columns: list, rows: list, limit: int = 50) -> str:
        """Turn query results into readable text for the LLM to summarize."""
        if not rows:
            return "No rows returned."

        lines = []
        for r in rows[:limit]:
            parts = [f"{k}: {v}" for k, v in r.items() if v is not None]
            lines.append(" | ".join(parts))

        text = "\n".join(lines)
        if len(rows) > limit:
            text += f"\n... and {len(rows) - limit} more rows"
        return text