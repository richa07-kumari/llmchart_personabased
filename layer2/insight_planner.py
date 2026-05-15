import json
import uuid
import os
from openai import OpenAI
from layer1.schema_store import SchemaStore

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class InsightPlanner:
    """
    Part 3 of Layer 2.

    Takes the ranked business questions from PersonaEngine and converts
    each one into a fully-specified chart blueprint. One LLM call per question.
    The output feeds directly into Part 4 (SQL generator) and Layer 3 (renderer).
    """

    SYSTEM_PROMPT = """You are a senior BI developer specialising in data visualisation.

You will receive:
1. A BUSINESS QUESTION to answer visually
2. The COLUMNS AVAILABLE for this question (with types, stats, sample values)
3. The SUGGESTED CHART TYPE from the analyst

Your job is to output a single JSON object — the complete chart specification.

Output format (return ONLY this JSON, no markdown, no explanation):
{
  "chart_type":   "line chart | bar chart | scatter plot | pie chart | heatmap | treemap | stacked bar",
  "title":        "Concise, professional chart title (max 8 words)",
  "x_axis": {
    "column":     "EXACT_COLUMN_NAME",
    "transform":  "NONE | MONTH | QUARTER | YEAR | MONTH_YEAR | TOP_N",
    "label":      "Axis label shown on chart",
    "top_n":      null
  },
  "y_axis": {
    "columns":      ["EXACT_COL_1", "EXACT_COL_2"],
    "aggregation":  "SUM | AVG | COUNT | COUNT_DISTINCT | MIN | MAX",
    "label":        "Axis label shown on chart"
  },
  "group_by":     "EXACT_COLUMN_NAME or null",
  "filters":      [{"column": "COL", "operator": "=|>|<|IN|!=", "value": "val"}],
  "sort_by":      "COLUMN ASC|DESC",
  "limit":        null,
  "insight_hint": "One sentence: what pattern to look for in this chart"
}

Rules:
- chart_type may differ from the suggestion if a better fit exists — justify via insight_hint
- x_axis.transform: use MONTH_YEAR for time series (formats as 'Jan 2023'), TOP_N for ranked bars
- x_axis.top_n: integer if transform=TOP_N (e.g. 10 for top 10), else null
- y_axis.columns: list even if only one column — always an array
- group_by: use when the chart needs series/colour split (e.g. PROFIT by REGION as grouped bars)
- filters: only add if the question implies a subset (e.g. "loss-making orders" → PROFIT < 0)
- sort_by: for ranked charts use the metric DESC; for time series use date col ASC
- limit: integer for TOP_N charts, null otherwise
- insight_hint: one sentence telling the viewer what anomaly or pattern to look for
- Return raw JSON only. No backticks. No preamble.
"""

    def __init__(self, schema: dict):
        self.schema = schema

    def _get_column_context(self, column_names: list[str]) -> str:
        """
        Builds a compact context block for the specific columns
        this question needs — not the full schema (saves tokens).
        Handles both list and dict formats for schema columns.
        """
        lines = ["COLUMNS AVAILABLE FOR THIS QUESTION:"]

        # Build lookup dict from columns (handle both list and dict formats)
        columns = self.schema.get("columns", [])
        if isinstance(columns, dict):
            column_lookup = columns
        elif isinstance(columns, list):
            # Convert list of column dicts to lookup dict by name
            column_lookup = {}
            for col in columns:
                if isinstance(col, dict) and "name" in col:
                    column_lookup[col["name"]] = col
            if not column_lookup:
                print(f"[InsightPlanner] WARNING: Could not build column lookup from list")
        else:
            column_lookup = {}
        
        print(f"[InsightPlanner] Column lookup type: {type(column_lookup)}, has {len(column_lookup)} columns")

        for col in column_names:
            meta = column_lookup.get(col, {})

            # Match exact field names from schema_cache.json
            dtype   = meta.get("data_type", "unknown")
            role    = meta.get("role", "unknown")
            desc    = meta.get("description", "")
            samples = meta.get("sample_values", None)
            min_val = meta.get("min_val")
            max_val = meta.get("max_val")

            line = f"  {col} [{dtype}, role={role}]: {desc}"

            if isinstance(samples, list) and samples:
                line += f" | samples: {', '.join(str(s) for s in samples[:3])}"
            
            if min_val is not None and max_val is not None:
                line += f" | range: {min_val} → {max_val}"

            lines.append(line)
        return "\n".join(lines)

    def _build_prompt(self, question: dict) -> str:
        """Assembles the user-turn prompt for one business question."""
        col_context = self._get_column_context(question["columns_needed"])
        return (
            f"BUSINESS QUESTION: {question['question']}\n\n"
            f"RATIONALE: {question['rationale']}\n\n"
            f"SUGGESTED CHART TYPE: {question['suggested_chart_type']}\n\n"
            f"{col_context}"
        )

    def _parse_spec(self, raw_text: str, question: dict) -> dict:
        """
        Parses and validates the LLM chart spec JSON.
        Injects chart_id and source question for traceability.
        """
        text = raw_text.strip()

        # Strip accidental markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)
        
        # Handle both dict and list responses from LLM
        if isinstance(parsed, list):
            if len(parsed) == 0:
                raise ValueError("LLM returned empty list")
            spec = parsed[0]  # Take first element
            print(f"    [*] LLM returned list, extracting first element")
        elif isinstance(parsed, dict):
            spec = parsed
        else:
            raise ValueError(f"Expected dict or list, got {type(parsed)}")

        # Validate mandatory top-level keys
        required = {
            "chart_type", "title", "x_axis",
            "y_axis", "group_by", "filters",
            "sort_by", "limit", "insight_hint"
        }
        missing = required - set(spec.keys())
        if missing:
            raise ValueError(f"Chart spec missing keys: {missing}")

        # Ensure y_axis.columns is always a list
        if isinstance(spec["y_axis"].get("columns"), str):
            spec["y_axis"]["columns"] = [spec["y_axis"]["columns"]]

        # Validate columns exist in schema (handle both list and dict formats)
        columns = self.schema.get("columns", [])
        if isinstance(columns, dict):
            valid_cols = set(columns.keys())
        else:
            valid_cols = set(col.get("name") for col in columns if isinstance(col, dict))

        all_spec_cols = (
            [spec["x_axis"].get("column")]
            + spec["y_axis"].get("columns", [])
            + ([spec["group_by"]] if spec.get("group_by") else [])
            + [f["column"] for f in spec.get("filters", [])]
        )
        bad_cols = [c for c in all_spec_cols if c and c not in valid_cols]
        if bad_cols:
            print(f"    [!] Spec references unknown columns {bad_cols} — may need review")

        # Inject metadata for downstream traceability
        spec["chart_id"]        = f"chart_{uuid.uuid4().hex[:6]}"
        spec["source_question"] = question["question"]
        spec["priority"]        = question["priority"]

        return spec

    def plan(self, questions: list[dict]) -> list[dict]:
        """
        Converts a list of business question dicts (from PersonaEngine)
        into a list of chart specification dicts.

        Makes one LLM call per question. Returns specs in same priority order.
        """
        print(f"\n[InsightPlanner] Planning {len(questions)} chart specs...")
        print(f"[InsightPlanner] Questions type: {type(questions)}")
        chart_specs = []

        for i, question in enumerate(questions, 1):
            print(f"  [{i}/{len(questions)}] Planning: \"{question['question'][:55]}...\"")

            prompt = self._build_prompt(question)
            print(f"    [*] Calling LLM...")

            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=600,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt}
                ]
            )
            raw_text = response.choices[0].message.content
            print(f"    [*] Response: {raw_text[:80]}...")
            
            spec = self._parse_spec(raw_text, question)
            
            if not isinstance(spec, dict):
                print(f"    ✗ ERROR: Parsed spec is {type(spec)}, not dict!")
                continue
            
            chart_specs.append(spec)

            print(f"    ✓ {spec['chart_type']} | x={spec['x_axis']['column']} | y={spec['y_axis']['columns']}")

        print(f"[InsightPlanner] ✓ Done — {len(chart_specs)} specs produced")
        print(f"[InsightPlanner] Specs type: {type(chart_specs)}")
        if chart_specs:
            print(f"[InsightPlanner] First spec type: {type(chart_specs[0])}")
        print()
        return chart_specs