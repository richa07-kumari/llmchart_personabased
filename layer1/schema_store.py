import json
import os
from datetime import datetime

CACHE_PATH = "layer1/schema_cache.json"

class SchemaStore:
    """
    Saves and loads the enriched semantic schema to/from a local JSON file.
    Layer 2 reads from this cache instead of re-running extraction every time.
    """

    def save(self, enriched_schema: dict, path: str = CACHE_PATH) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(enriched_schema, f, indent=2, default=str)
        print(f"[SchemaStore] Schema saved → {path}")

    def load(self, path: str = CACHE_PATH) -> dict:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"No cached schema found at {path}. Run the pipeline first."
            )
        with open(path, "r") as f:
            schema = json.load(f)
        print(f"[SchemaStore] Loaded schema from {path} "
              f"(extracted at: {schema.get('extracted_at', 'unknown')})")
        return schema

    def is_stale(self, path: str = CACHE_PATH, max_age_hours: int = 24) -> bool:
        """Returns True if cache is older than max_age_hours — triggers a refresh."""
        if not os.path.exists(path):
            return True
        with open(path, "r") as f:
            schema = json.load(f)
        extracted_at = schema.get("extracted_at", "")
        try:
            age = datetime.utcnow() - datetime.fromisoformat(extracted_at)
            return age.total_seconds() > max_age_hours * 3600
        except Exception:
            return True