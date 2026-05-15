import os
from openai import OpenAI
import pandas as pd

client = OpenAI()  


class NarrativeEngine:
    """
    Generates a one-sentence plain-English insight for each chart,
    grounded in the actual data returned — not generic commentary.
    """

    SYSTEM_PROMPT = """You are a concise data analyst presenting findings to a business executive.
Given a chart's data summary and an insight hint, write exactly ONE sentence (max 30 words)
that calls out the most important pattern, anomaly, or finding in the data.
Be specific — use actual numbers from the data. No vague statements.
Return only the sentence. No preamble, no bullet points."""

    def generate(self, result: dict) -> str:
        """
        Generates a narrative sentence for one chart result.

        Args:
            result: a result dict with 'dataframe', 'title', 'insight_hint'

        Returns:
            A single insight sentence string, or a fallback if the call fails.
        """
        df          = result.get("dataframe", pd.DataFrame())
        title       = result.get("title", "")
        hint        = result.get("insight_hint", "")

        if df.empty:
            return "No data available for this chart."

        # Build a compact data summary — top 5 rows only to save tokens
        data_preview = df.head(5).to_string(index=False)

        prompt = (
            f"Chart title: {title}\n"
            f"Insight hint: {hint}\n\n"
            f"Data (top 5 rows):\n{data_preview}\n\n"
            f"Total rows in dataset: {len(df)}"
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=80,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt}
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"  [Narrative] Failed for '{title}': {e}")
            return hint  # fallback to the insight_hint from the spec