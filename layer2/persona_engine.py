import json
import os
from openai import OpenAI
from layer2.persona_registry import PersonaRegistry
from layer1.schema_store import SchemaStore

client = OpenAI()  


class PersonaEngine:
    """
    Part 2 of Layer 2.

    Takes a persona name + enriched schema, calls the LLM once,
    and returns a ranked list of business questions — each grounded
    in the actual columns available in the Snowflake dataset.
    """

    SYSTEM_PROMPT = """You are a senior business intelligence consultant.

Your job is to analyse a retail dataset schema and a business persona, then
identify the most valuable analytical questions this person should be asking.

You will be given:
1. A PERSONA BLOCK — the role, their KPIs, and what decisions they make
2. A SCHEMA BLOCK — every column in the dataset with its data type,
   business description, column role, and insight tags

Your output must be a JSON array of business questions. Each element:
{
  "question":           "Plain English question this chart will answer",
  "rationale":          "One sentence: why this matters for this persona",
  "priority":           "high | medium | low",
  "columns_needed":     ["EXACT_COL_NAME_1", "EXACT_COL_NAME_2"],
  "suggested_chart_type": "line chart | bar chart | scatter plot | pie chart | heatmap | treemap"
}

Rules:
- Return ONLY the JSON array. No explanation, no markdown fences.
- Generate exactly 5 questions: 2 high priority, 2 medium, 1 low.
- columns_needed must only contain column names that exist in the schema.
- Questions must be answerable from the available columns — no invented metrics.
- Prioritise questions that reveal trends, comparisons, or anomalies — not raw totals.
- Avoid questions the persona config explicitly says to avoid.
- Each question should lead to a DIFFERENT chart — no two questions should
  produce the same chart type with the same axes.
"""

    def __init__(self, schema: dict, registry: PersonaRegistry):
        self.schema   = schema
        self.registry = registry

    def _build_schema_summary(self) -> str:
        """
        Converts the enriched schema into a compact LLM-readable block.
        Only includes fields the LLM needs — avoids token bloat.
        """
        lines = ["AVAILABLE COLUMNS:"]
        columns = self.schema.get("columns", [])
        
        # Handle both list and dict formats
        if isinstance(columns, dict):
            columns = columns.items()
        else:
            # Convert list of column dicts to (name, meta) tuples
            columns = [(col.get("name"), col) for col in columns]
        
        for col_name, meta in columns:
            role    = meta.get("role", "unknown")
            dtype   = meta.get("data_type", "")
            desc    = meta.get("description", "")
            tags    = ", ".join(meta.get("chart_types", []))
            samples = meta.get("sample_values", None)
            min_val = meta.get("min_val")
            max_val = meta.get("max_val")

            line = f"  {col_name} [{dtype}, role={role}]: {desc}"
            if tags:
                line += f" | chart_types: {tags}"
            if isinstance(samples, list) and samples:
                line += f" | samples: {', '.join(str(s) for s in samples[:3])}"
            if min_val is not None and max_val is not None:
                line += f" | range: {min_val} to {max_val}"
            lines.append(line)

        lines.append(f"\nTotal rows in table: {self.schema.get('total_rows', 'unknown')}")
        return "\n".join(lines)

    def _build_user_prompt(self, persona_role: str) -> str:
        """Assembles the full user-turn prompt sent to the LLM."""
        persona_block = self.registry.to_llm_context(persona_role)
        schema_block  = self._build_schema_summary()
        return f"{persona_block}\n\n{'─' * 60}\n\n{schema_block}"

    def _parse_response(self, raw_text: str) -> list[dict]:
        """
        Parses and validates the LLM JSON response.
        Strips accidental markdown fences, validates required keys.
        Handles both list and dict responses from LLM.
        """
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)
        
        # Handle both list and dict responses
        if isinstance(parsed, dict):
            # Single object - wrap in list
            questions = [parsed]
            print(f"  [*] LLM returned single object, wrapping in list")
        elif isinstance(parsed, list):
            questions = parsed
        else:
            raise ValueError(f"Expected list or dict, got {type(parsed)}")

        required_keys = {
            "question", "rationale", "priority",
            "columns_needed", "suggested_chart_type"
        }
        
        # Get valid column names from schema (handle both list and dict formats)
        columns = self.schema.get("columns", [])
        if isinstance(columns, dict):
            valid_cols = set(columns.keys())
        else:
            valid_cols = set(col.get("name") for col in columns if isinstance(col, dict))

        validated = []
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                print(f"  [!] Question {i+1} is not a dict, skipping")
                continue
                
            missing = required_keys - set(q.keys())
            if missing:
                print(f"  [!] Question {i+1} missing keys {missing} — skipping")
                continue

            # Validate that columns_needed exist in schema
            bad_cols = [c for c in q["columns_needed"] if c not in valid_cols]
            if bad_cols:
                print(f"  [!] Question {i+1} references unknown columns {bad_cols} — removing them")
                q["columns_needed"] = [c for c in q["columns_needed"] if c in valid_cols]

            # Normalise priority
            if q["priority"] not in ("high", "medium", "low"):
                q["priority"] = "medium"

            validated.append(q)

        return validated

    def generate(self, persona_role: str) -> list[dict]:
        """
        Main entry point. Returns a validated list of business question dicts
        ranked by priority (high first).

        Args:
            persona_role: e.g. "ceo", "sales_officer", "cfo"

        Returns:
            List of dicts, each with: question, rationale, priority,
            columns_needed, suggested_chart_type
        """
        print(f"\n[PersonaEngine] Generating insights for persona: '{persona_role}'...")

        # Validate persona exists before making the API call
        persona = self.registry.get(persona_role)
        print(f"  Persona resolved: {persona.display_name}")

        user_prompt = self._build_user_prompt(persona_role)

        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1200,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt}
            ]
        )
        raw_text = response.choices[0].message.content
        questions = self._parse_response(raw_text)

        # Sort: high → medium → low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        questions.sort(key=lambda q: priority_order.get(q["priority"], 1))

        print(f"  [PersonaEngine] {len(questions)} questions generated "
              f"({sum(1 for q in questions if q['priority']=='high')} high priority)")

        return questions