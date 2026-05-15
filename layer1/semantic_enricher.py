import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class SemanticEnricher:
    """
    Takes the raw metadata dict from MetadataExtractor and uses an LLM
    to annotate every column with business meaning, role, aggregations,
    and chart hints — producing the final semantic schema for Layer 2.
    """

    def __init__(self):
        self.client =OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model  = "gpt-4o"

    # ─── System prompt: tells the LLM exactly what to output ──────────────────

    def _build_system_prompt(self) -> str:
        return """
You are a semantic data analyst. You receive raw column metadata from a
business dataset and your job is to enrich each column with business context.

For every column you will output a JSON object with these exact fields:

{
  "name": "<COLUMN_NAME>",
  "description": "<1 sentence plain-English description of what this column represents>",
  "role": "<one of: dimension | measure | filter | identifier>",
  "aggregations": ["<list of valid SQL aggregations, e.g. SUM, AVG, COUNT, MIN, MAX, trend>"],
  "chart_types": ["<list of chart types this column works well in, e.g. line, bar, pie, scatter, map, KPI card>"],
  "is_filterable": <true | false>,
  "is_groupable":  <true | false>,
  "business_notes": "<any important caveats e.g. 'can be negative (returns/discounts)', 'only 3 categories', 'date — supports time-series'>",
  "example_questions": ["<2 example business questions this column can help answer>"]
}

Role definitions:
- dimension:  A categorical or date column used to GROUP BY or label axes (e.g. REGION, CATEGORY, ORDER_DATE)
- measure:    A numeric column that gets aggregated (e.g. SALES, PROFIT, QUANTITY)
- filter:     A column primarily used to slice/filter data, often low-cardinality (e.g. SEGMENT, SHIP_MODE)
- identifier: A unique key or ID column — skip for charts (e.g. ROW_ID, ORDER_ID, CUSTOMER_ID)

Return ONLY a valid JSON array of enriched column objects. No markdown, no explanation.
No ```json fences. Just the raw JSON array.
""".strip()

    # ─── User prompt: injects the actual metadata ──────────────────────────────

    def _build_user_prompt(self, metadata: dict) -> str:
        table_name  = metadata["table_name"]
        total_rows  = metadata["total_rows"]
        columns     = metadata["columns"]

        # Format each column compactly for the prompt
        col_descriptions = []
        for col in columns:
            col_descriptions.append(
                f"- {col['name']} | type: {col['data_type']} | "
                f"nulls: {col['null_count']} | unique: {col['unique_count']} | "
                f"min: {col['min_val']} | max: {col['max_val']} | "
                f"samples: {col['sample_values']}"
            )

        cols_text = "\n".join(col_descriptions)

        return f"""
Dataset: {table_name}
Total rows: {total_rows}

Columns:
{cols_text}

Enrich every column listed above. Return a JSON array with one object per column.
""".strip()

    # ─── Call the LLM and parse the response ──────────────────────────────────

    def _call_llm(self, system_prompt: str, user_prompt: str) -> list[dict]:
        response = self.client.chat.completions.create(
            model="gpt-4o",
            max_tokens=400,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ]
        )

        raw_text = response.choices[0].message.content.strip()

        try:
            enriched_columns = json.loads(raw_text)
        except json.JSONDecodeError as e:
            # Fallback: strip any accidental fences and retry
            cleaned = raw_text.replace("```json", "").replace("```", "").strip()
            enriched_columns = json.loads(cleaned)

        return enriched_columns

    # ─── Merge: attach LLM annotations back onto original metadata ────────────

    def _merge(self, raw_metadata: dict, enriched_columns: list[dict]) -> dict:
        """
        Index enriched columns by name and merge with the original
        raw metadata so nothing is lost (stats, sample values remain).
        """
        enriched_index = {col["name"]: col for col in enriched_columns}

        merged_columns = []
        for raw_col in raw_metadata["columns"]:
            col_name    = raw_col["name"]
            enriched    = enriched_index.get(col_name, {})

            merged_columns.append({
                # Preserve all raw stats
                **raw_col,
                # Layer on LLM annotations
                "description":      enriched.get("description", ""),
                "role":             enriched.get("role", "unknown"),
                "aggregations":     enriched.get("aggregations", []),
                "chart_types":      enriched.get("chart_types", []),
                "is_filterable":    enriched.get("is_filterable", False),
                "is_groupable":     enriched.get("is_groupable", False),
                "business_notes":   enriched.get("business_notes", ""),
                "example_questions":enriched.get("example_questions", []),
            })

        return {
            "table_name":    raw_metadata["table_name"],
            "total_rows":    raw_metadata["total_rows"],
            "columns":       merged_columns,
            # Convenience indexes for Layer 2 fast lookup
            "measures":      [c["name"] for c in merged_columns if c["role"] == "measure"],
            "dimensions":    [c["name"] for c in merged_columns if c["role"] == "dimension"],
            "filters":       [c["name"] for c in merged_columns if c["role"] == "filter"],
            "identifiers":   [c["name"] for c in merged_columns if c["role"] == "identifier"],
        }

    # ─── Main entry point ─────────────────────────────────────────────────────

    def enrich(self, raw_metadata: dict) -> dict:
        """
        Takes the dict from MetadataExtractor.extract() and returns
        a fully enriched semantic schema dict.
        """
        print(f"[SemanticEnricher] Enriching {len(raw_metadata['columns'])} columns via LLM...")

        system_prompt    = self._build_system_prompt()
        user_prompt      = self._build_user_prompt(raw_metadata)
        enriched_columns = self._call_llm(system_prompt, user_prompt)

        semantic_schema  = self._merge(raw_metadata, enriched_columns)

        print(f"[SemanticEnricher] Done.")
        print(f"  Measures:    {semantic_schema['measures']}")
        print(f"  Dimensions:  {semantic_schema['dimensions']}")
        print(f"  Filters:     {semantic_schema['filters']}")
        print(f"  Identifiers: {semantic_schema['identifiers']}")

        return semantic_schema
