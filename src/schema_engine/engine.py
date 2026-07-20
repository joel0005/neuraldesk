"""
Schema Engine — The Schema-First Pipeline.

RULE: When client uploads ANY data (database, Excel, CSV), this runs FIRST.
Auto-clean → auto-detect → AI understand → client review → save glossary → THEN embed.
"""

import re
import json
import logging
from ..config import config

logger = logging.getLogger(__name__)


class SchemaEngine:

    # Common null representations
    NULL_VALUES = {"", "null", "none", "na", "n/a", "-", "nan", "nil", "#n/a", "missing", "undefined"}

    def profile(self, df, table_name="data") -> dict:
        """Step 1: Scan data and detect types, quality, issues."""
        import pandas as pd

        columns = []
        for col in df.columns:
            series = df[col]
            null_mask = series.isna() | series.astype(str).str.lower().str.strip().isin(self.NULL_VALUES)
            null_pct = round(null_mask.sum() / max(len(series), 1) * 100, 1)
            valid = series[~null_mask].astype(str).str.strip()

            # Detect type
            col_type = self._detect_type(valid, str(col))

            # Sample values
            samples = valid.drop_duplicates().head(5).tolist()

            # Unique values (for category columns)
            unique_vals = valid.value_counts().head(10).index.tolist() if valid.nunique() <= 20 else []

            # Quality
            if null_pct > 80:
                quality = "unusable"
            elif null_pct > 30:
                quality = "poor"
            elif null_pct > 5:
                quality = "moderate"
            else:
                quality = "good"

            columns.append({
                "original_name": str(col),
                "clean_name": self._clean_name(str(col)),
                "type": col_type,
                "samples": samples,
                "unique_values": unique_vals,
                "null_pct": null_pct,
                "unique_count": int(valid.nunique()),
                "quality": quality,
                "suggest_exclude": null_pct > 80,
                "needs_input": self._is_unclear(str(col)),
            })

        return {
            "table_name": table_name,
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "columns": columns,
        }

    def clean(self, df) -> tuple:
        """Step 2: Auto-clean obvious issues. Returns (cleaned_df, changes_list)."""
        import pandas as pd
        df = df.copy()
        changes = []

        # Standardize nulls
        for col in df.columns:
            mask = df[col].astype(str).str.lower().str.strip().isin(self.NULL_VALUES)
            if mask.any():
                count = int(mask.sum())
                df.loc[mask, col] = None
                changes.append(f"Standardized {count} null values in '{col}'")

        # Remove empty rows
        empty = df.isna().all(axis=1)
        if empty.any():
            count = int(empty.sum())
            df = df[~empty].reset_index(drop=True)
            changes.append(f"Removed {count} empty rows")

        # Remove empty columns
        empty_cols = df.columns[df.isna().all()]
        if len(empty_cols) > 0:
            df = df.drop(columns=empty_cols)
            changes.append(f"Removed {len(empty_cols)} empty columns")

        # Strip whitespace
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "None": None})

        # Remove duplicates
        dupes = int(df.duplicated().sum())
        if dupes > 0:
            df = df.drop_duplicates().reset_index(drop=True)
            changes.append(f"Removed {dupes} duplicate rows")

        return df, changes

    def ai_understand(self, columns: list, table_name: str, llm_router=None) -> list:
        """Step 3: Use AI to understand unclear column names."""
        if not llm_router:
            return columns

        unclear = [c for c in columns if c.get("needs_input")]
        if not unclear:
            return columns

        from ..llm.base import LLMMessage

        col_info = []
        for c in unclear:
            info = f"- Column: '{c['original_name']}' | Type: {c['type']} | Samples: {c['samples'][:3]}"
            if c.get("unique_values"):
                info += f" | Values: {c['unique_values'][:5]}"
            col_info.append(info)

        prompt = f"""Analyze this database table '{table_name}'.
These columns have unclear names. Describe what each contains.

{chr(10).join(col_info)}

Respond in JSON only, no markdown:
{{"columns": [{{"original_name": "col1", "description": "Customer name", "suggested_name": "customer_name"}}]}}"""

        try:
            response = llm_router.generate(
                messages=[
                    LLMMessage(role="system", content="You are a data analyst. Respond only with valid JSON."),
                    LLMMessage(role="user", content=prompt),
                ],
                temperature=0.1,
                max_tokens=500,
            )

            text = response.content.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(text)

            ai_map = {c["original_name"]: c for c in result.get("columns", [])}
            for col in columns:
                if col["original_name"] in ai_map:
                    ai_data = ai_map[col["original_name"]]
                    col["ai_description"] = ai_data.get("description", "")
                    col["clean_name"] = self._clean_name(ai_data.get("suggested_name", col["clean_name"]))
                    col["needs_input"] = False

        except Exception as e:
            logger.warning(f"AI understanding failed: {e}")

        return columns

    def build_glossary(self, profile: dict, client_edits: dict = None) -> dict:
        """Step 4: Build permanent business glossary from profile + client edits."""
        client_edits = client_edits or {}

        glossary = {
            "table_name": profile["table_name"],
            "total_rows": profile["total_rows"],
            "columns": {},
            "value_maps": {},
        }

        for col in profile["columns"]:
            edits = client_edits.get(col["original_name"], {})

            if edits.get("exclude", col.get("suggest_exclude")):
                continue

            glossary["columns"][col["original_name"]] = {
                "display_name": edits.get("clean_name", col.get("clean_name", col["original_name"])),
                "type": col["type"],
                "description": edits.get("description", col.get("ai_description", col["clean_name"])),
                "samples": col.get("samples", [])[:3],
            }

            if edits.get("value_map"):
                glossary["value_maps"][col["original_name"]] = edits["value_map"]

        return glossary

    def glossary_to_text(self, glossary: dict) -> str:
        """Convert glossary to text that the LLM reads as context."""
        lines = [f"Table: {glossary['table_name']}", f"Rows: {glossary.get('total_rows', '?')}", "", "Columns:"]

        for name, info in glossary.get("columns", {}).items():
            line = f"  - {name} ({info['type']}): {info['description']}"
            if info.get("samples"):
                line += f" | Examples: {', '.join(str(s) for s in info['samples'])}"
            lines.append(line)

        for col, mapping in glossary.get("value_maps", {}).items():
            for code, meaning in mapping.items():
                lines.append(f"  - {col}={code} means '{meaning}'")

        return "\n".join(lines)

    # ── Helpers ──

    def _detect_type(self, values, col_name: str) -> str:
        if len(values) == 0:
            return "unknown"

        col_lower = col_name.lower()
        if any(k in col_lower for k in ["email", "mail"]):
            return "email"
        if any(k in col_lower for k in ["phone", "mobile", "tel"]):
            return "phone"
        if any(k in col_lower for k in ["date", "created_at", "updated_at", "timestamp"]):
            return "datetime"
        if col_lower in ("id",) or col_lower.endswith("_id"):
            return "id"

        sample = values.head(50)
        nums = 0
        for v in sample:
            try:
                float(str(v).replace(",", ""))
                nums += 1
            except ValueError:
                pass

        if nums > len(sample) * 0.7:
            return "number"
        if values.nunique() <= 20 and len(values) > 20:
            return "category"
        return "text"

    def _clean_name(self, name: str) -> str:
        name = re.sub(r'[\s\-\.]+', '_', str(name).strip())
        name = re.sub(r'[^a-zA-Z0-9_]', '', name)
        name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)
        return re.sub(r'_+', '_', name.lower().strip('_')) or "unnamed"

    def _is_unclear(self, name: str) -> bool:
        name = name.lower().strip()
        if len(name) <= 2:
            return True
        if re.match(r'^(col|field|column|c|f)\d+$', name):
            return True
        if name in ("col1", "col2", "field1", "data", "value", "val", "tmp"):
            return True
        return False