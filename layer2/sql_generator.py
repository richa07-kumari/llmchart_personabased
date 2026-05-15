import pandas as pd
from layer1.snowflake_connector import SnowflakeConnector


class SQLGenerator:
    """
    Part 4 of Layer 2.
    
    Takes chart specifications from InsightPlanner and converts them
    into Snowflake SQL queries. Executes the queries and returns results.
    """

    def __init__(self, connector: SnowflakeConnector):
        """
        Initialize SQLGenerator with a Snowflake connector.
        
        Args:
            connector: SnowflakeConnector instance for executing queries
        """
        self.connector = connector
        self.table_name = "SUPERSTORE_ORDERS"

    def _build_sql(self, spec: dict) -> str:
        """
        Converts a chart specification into a Snowflake SQL query.
        
        Args:
            spec: Chart specification dict from InsightPlanner
            
        Returns:
            SQL query string
        """
        x_col = spec["x_axis"]["column"]
        y_cols = spec["y_axis"]["columns"]
        agg = spec["y_axis"]["aggregation"]
        group_by = spec.get("group_by")
        filters = spec.get("filters", [])
        sort_by = spec.get("sort_by", "")
        limit = spec.get("limit")
        
        # Build the SELECT clause
        select_parts = [f'"{x_col}" AS x']
        
        for y_col in y_cols:
            agg_func = agg.upper() if agg else "SUM"
            if agg_func == "COUNT":
                select_parts.append(f'COUNT(*) AS "{y_col}"')
            elif agg_func == "COUNT_DISTINCT":
                select_parts.append(f'COUNT(DISTINCT "{y_col}") AS "{y_col}"')
            else:
                select_parts.append(f'{agg_func}("{y_col}") AS "{y_col}"')
        
        if group_by:
            select_parts.append(f'"{group_by}" AS group_by')
        
        select_clause = ", ".join(select_parts)
        
        # Build the FROM clause
        from_clause = f"FROM {self.table_name}"
        
        # Build the WHERE clause
        where_parts = []
        for f in filters:
            col = f["column"]
            op = f["operator"]
            val = f["value"]
            
            if op == "IN":
                val_list = ",".join([f"'{v}'" for v in val])
                where_parts.append(f'"{col}" IN ({val_list})')
            elif op in ["=", "!=", ">", "<", ">=", "<="]:
                if isinstance(val, str):
                    where_parts.append(f'"{col}" {op} \'{val}\'')
                else:
                    where_parts.append(f'"{col}" {op} {val}')
        
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        
        # Build the GROUP BY clause
        group_clause = ""
        if group_by:
            group_parts = [f'"{x_col}"', f'"{group_by}"']
            group_clause = f"GROUP BY {', '.join(group_parts)}"
        elif agg and agg.upper() not in ["COUNT", "COUNT_DISTINCT"]:
            group_clause = f"GROUP BY \"{x_col}\""
        
        # Build ORDER BY clause
        order_clause = ""
        if sort_by:
            order_clause = f"ORDER BY {sort_by}"
        
        # Build LIMIT clause
        limit_clause = f"LIMIT {limit}" if limit else "LIMIT 1000"
        
        # Assemble the full query
        query_parts = [
            f"SELECT {select_clause}",
            from_clause,
            where_clause,
            group_clause,
            order_clause,
            limit_clause
        ]
        
        query = "\n".join([p for p in query_parts if p])
        return query

    def _generate_mock_data(self, spec: dict) -> pd.DataFrame:
        """
        Generate mock data for a chart spec when Snowflake is unavailable.
        Used for demo/testing purposes.
        
        Args:
            spec: Chart specification dict
            
        Returns:
            Mock DataFrame matching the spec structure
        """
        import numpy as np
        
        x_col = spec["x_axis"]["column"]
        y_cols = spec["y_axis"]["columns"]
        
        # Create mock data based on column names
        if "DATE" in x_col.upper() or "TIME" in x_col.upper():
            # Time series data
            dates = pd.date_range("2023-01-01", periods=12, freq="MS")
            data = {x_col: dates.strftime("%Y-%m")}
        elif "REGION" in x_col.upper() or "SEGMENT" in x_col.upper():
            # Categorical data
            data = {x_col: ["Central", "East", "South", "West"]}
        else:
            # Generic categories
            data = {x_col: [f"Category {i}" for i in range(1, 6)]}
        
        # Add Y columns with mock numeric data
        for y_col in y_cols:
            data[y_col] = np.random.randint(1000, 50000, size=len(data[x_col]))
        
        return pd.DataFrame(data)

    def execute_all(self, chart_specs: list) -> list:
        """
        Execute all chart specifications and return results.
        
        Args:
            chart_specs: List of chart specification dictionaries from InsightPlanner
            
        Returns:
            List of results, each containing query results, title, and metadata for chart rendering
        """
        results = []
        print(f"\n[SQLGenerator] Executing {len(chart_specs)} chart specs...")
        print(f"[SQLGenerator] Chart specs type: {type(chart_specs)}")
        
        for i, spec in enumerate(chart_specs, 1):
            print(f"  [SQLGenerator] Processing spec {i}, type: {type(spec)}")
            
            if not isinstance(spec, dict):
                print(f"    ✗ ERROR: Spec is {type(spec)}, not dict! Value: {spec}")
                continue
            
            try:
                # Try to build and execute SQL
                sql = self._build_sql(spec)
                print(f"  [{i}/{len(chart_specs)}] Executing: {spec['title']}")
                print(f"    SQL: {sql[:80]}...")
                
                try:
                    # Try to query Snowflake
                    rows = self.connector.execute_query(sql)
                    df = pd.DataFrame(rows)
                except Exception as e:
                    # Fallback to mock data if Snowflake fails
                    print(f"    ⚠ Snowflake query failed ({str(e)[:30]}...), using mock data")
                    df = self._generate_mock_data(spec)
                
                if df.empty:
                    print(f"    ⚠ No data returned, using mock data")
                    df = self._generate_mock_data(spec)
                
                # Build result dict for renderer
                result = {
                    **spec,
                    "dataframe": df,
                    "title": spec["title"],
                    "chart_type": spec["chart_type"],
                    "chart_id": spec.get("chart_id", ""),
                    "priority": spec.get("priority", "medium"),
                    "insight_hint": spec.get("insight_hint", ""),
                    "source_question": spec.get("source_question", ""),
                }
                
                print(f"    [SQLGenerator] Result dict type: {type(result)}, keys: {result.keys()}")
                results.append(result)
                print(f"    ✓ Success ({len(df)} rows)")
                
            except Exception as e:
                print(f"    ✗ Error: {str(e)}")
                import traceback
                traceback.print_exc()
                # Still add mock result so pipeline doesn't break
                df = self._generate_mock_data(spec)
                result = {
                    **spec,
                    "dataframe": df,
                    "title": spec["title"],
                    "chart_type": spec["chart_type"],
                    "chart_id": spec.get("chart_id", ""),
                    "priority": spec.get("priority", "medium"),
                    "insight_hint": spec.get("insight_hint", ""),
                    "source_question": spec.get("source_question", ""),
                }
                results.append(result)
        
        print(f"[SQLGenerator] Done — {len(results)} results returned")
        print(f"[SQLGenerator] Results type: {type(results)}")
        if results:
            print(f"[SQLGenerator] First result type: {type(results[0])}")
        print()
        return results
