import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from typing import Any
from layer1.snowflake_connector import SnowflakeConnector


class MetadataExtractor:

    def __init__(self, connector: SnowflakeConnector, table_name: str = "SUPERSTORE_ORDERS"):
        self.connector  = connector
        self.table_name = table_name.upper()

    def _normalize(self, rows: list) -> list[dict]:
        """Convert Snowflake DictCursor rows to plain lowercase-key dicts."""
        return [{k.lower(): v for k, v in row.items()} for row in rows]

    def _get_column_definitions(self) -> list[dict]:
        query = f"""
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                IS_NULLABLE,
                ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME   = '{self.table_name}'
              AND TABLE_SCHEMA = CURRENT_SCHEMA()
            ORDER BY ORDINAL_POSITION
        """
        rows = self.connector.execute_query(query)
        return self._normalize(rows)

    def _get_column_stats(self, columns: list[dict]) -> dict[str, dict]:
        stat_selects = []

        for col in columns:
            col_name  = col["column_name"]
            data_type = col["data_type"].upper()

            is_numeric = any(t in data_type for t in ["NUMBER", "FLOAT", "INT", "DECIMAL", "DOUBLE"])
            is_date    = any(t in data_type for t in ["DATE", "TIMESTAMP", "TIME"])

            if is_numeric or is_date:
                stat_selects.append(f"""
                    SELECT
                        '{col_name}'                       AS col_name,
                        COUNT(*)                           AS total_rows,
                        COUNT(*) - COUNT("{col_name}")     AS null_count,
                        COUNT(DISTINCT "{col_name}")       AS unique_count,
                        TO_VARCHAR(MIN("{col_name}"))      AS min_val,
                        TO_VARCHAR(MAX("{col_name}"))      AS max_val
                    FROM {self.table_name}
                """)
            else:
                stat_selects.append(f"""
                    SELECT
                        '{col_name}'                       AS col_name,
                        COUNT(*)                           AS total_rows,
                        COUNT(*) - COUNT("{col_name}")     AS null_count,
                        COUNT(DISTINCT "{col_name}")       AS unique_count,
                        NULL                               AS min_val,
                        NULL                               AS max_val
                    FROM {self.table_name}
                """)

        union_query = "\nUNION ALL\n".join(stat_selects)
        rows = self.connector.execute_query(union_query)
        rows = self._normalize(rows)
        return {row["col_name"]: row for row in rows}

    def _get_sample_values(self, columns: list[dict], n_samples: int = 5) -> dict[str, list]:
        col_names = ', '.join([f'"{c["column_name"]}"' for c in columns])

        query = f"""
            SELECT {col_names}
            FROM {self.table_name}
            TABLESAMPLE SYSTEM (1)
            LIMIT {n_samples * 10}
        """
        rows = self.connector.execute_query(query)
        rows = self._normalize(rows)
        df   = pd.DataFrame(rows)

        sample_map = {}
        for col in columns:
            col_name = col["column_name"]
            key      = col_name.lower()

            if key in df.columns:
                vals = df[key].dropna().unique().tolist()[:n_samples]
                sample_map[col_name] = [str(v) for v in vals]
            else:
                sample_map[col_name] = []

        return sample_map

    def extract(self) -> dict[str, Any]:
        print(f"[MetadataExtractor] Starting extraction for: {self.table_name}")

        col_defs = self._get_column_definitions()
        print(f"[MetadataExtractor] Found {len(col_defs)} columns")

        stats = self._get_column_stats(col_defs)
        print(f"[MetadataExtractor] Stats computed for all columns")

        samples = self._get_sample_values(col_defs)
        print(f"[MetadataExtractor] Sample values pulled")

        total_rows = list(stats.values())[0]["total_rows"] if stats else 0

        column_profiles = []
        for col in col_defs:
            col_name = col["column_name"]
            stat     = stats.get(col_name, {})

            column_profiles.append({
                "name":          col_name,
                "data_type":     col["data_type"],
                "is_nullable":   col["is_nullable"],
                "null_count":    stat.get("null_count", 0),
                "unique_count":  stat.get("unique_count", 0),
                "min_val":       stat.get("min_val"),
                "max_val":       stat.get("max_val"),
                "sample_values": samples.get(col_name, []),
            })

        metadata = {
            "table_name": self.table_name,
            "total_rows": total_rows,
            "columns":    column_profiles,
        }

        print(f"[MetadataExtractor] Done — {total_rows} rows, {len(column_profiles)} columns")
        return metadata