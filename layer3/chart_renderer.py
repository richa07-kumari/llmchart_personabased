import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

PLOTLY_THEME = "plotly_white"
COLOR_SEQ    = px.colors.qualitative.Set2


class ChartRenderer:
    """
    Converts a result dict (chart spec + DataFrame) into a Plotly figure.
    Handles all chart types the InsightPlanner can produce.
    """

    def render(self, result: dict) -> go.Figure:
        """
        Main entry point. Routes to the correct chart builder
        based on chart_type in the spec. Returns a Plotly Figure.
        """
        chart_type = result.get("chart_type", "bar chart").lower()
        df         = result["dataframe"]
        spec       = result

        if df.empty:
            return self._empty_figure(result.get("title", "No data"))

        # Normalise column names to lowercase (Snowflake returns uppercase)
        df.columns = [c.lower() for c in df.columns]

        dispatch = {
            "line chart":   self._line_chart,
            "bar chart":    self._bar_chart,
            "scatter plot": self._scatter_plot,
            "pie chart":    self._pie_chart,
            "heatmap":      self._heatmap,
            "treemap":      self._treemap,
            "stacked bar":  self._stacked_bar,
        }

        builder = dispatch.get(chart_type, self._bar_chart)
        fig     = builder(df, spec)
        fig     = self._apply_theme(fig, spec)
        return fig

    # ─────────────────────────────────────────────
    # Chart builders
    # ─────────────────────────────────────────────
    def _line_chart(self, df: pd.DataFrame, spec: dict) -> go.Figure:
        x_col   = df.columns[0]
        y_cols  = [c.lower() for c in spec["y_axis"]["columns"]
                   if c.lower() in df.columns]
        fig = px.line(
            df, x=x_col, y=y_cols,
            labels={x_col: spec["x_axis"]["label"],
                    "value": spec["y_axis"]["label"]},
            color_discrete_sequence=COLOR_SEQ,
            markers=True,
        )
        fig.update_traces(line=dict(width=2.5))
        return fig

    def _bar_chart(self, df: pd.DataFrame, spec: dict) -> go.Figure:
        x_col  = df.columns[0]
        y_cols = [c.lower() for c in spec["y_axis"]["columns"]
                  if c.lower() in df.columns]
        group  = spec.get("group_by", "").lower() if spec.get("group_by") else None

        if group and group in df.columns:
            fig = px.bar(
                df, x=x_col, y=y_cols[0], color=group,
                barmode="group",
                color_discrete_sequence=COLOR_SEQ,
            )
        else:
            # Multi-metric grouped bar
            if len(y_cols) > 1:
                df_melt = df.melt(id_vars=[x_col], value_vars=y_cols,
                                  var_name="metric", value_name="value")
                fig = px.bar(
                    df_melt, x=x_col, y="value", color="metric",
                    barmode="group",
                    color_discrete_sequence=COLOR_SEQ,
                )
            else:
                # Single metric — colour bars by value (negative = red)
                y = y_cols[0]
                colors = ["#E05C5C" if v < 0 else "#4C9BE8"
                          for v in df[y]]
                fig = go.Figure(go.Bar(
                    x=df[x_col], y=df[y],
                    marker_color=colors,
                    name=y.upper(),
                ))

        fig.update_layout(xaxis_tickangle=-35)
        return fig

    def _scatter_plot(self, df: pd.DataFrame, spec: dict) -> go.Figure:
        x_col  = df.columns[0]
        y_cols = [c.lower() for c in spec["y_axis"]["columns"]
                  if c.lower() in df.columns]
        y_col  = y_cols[0] if y_cols else df.columns[1]
        color  = spec.get("group_by", "").lower() if spec.get("group_by") else None

        fig = px.scatter(
            df, x=x_col, y=y_col,
            color=color if color and color in df.columns else None,
            trendline="ols",
            color_discrete_sequence=COLOR_SEQ,
            opacity=0.65,
        )
        return fig

    def _pie_chart(self, df: pd.DataFrame, spec: dict) -> go.Figure:
        label_col = df.columns[0]
        y_cols    = [c.lower() for c in spec["y_axis"]["columns"]
                     if c.lower() in df.columns]
        value_col = y_cols[0] if y_cols else df.columns[1]

        fig = px.pie(
            df, names=label_col, values=value_col,
            color_discrete_sequence=COLOR_SEQ,
            hole=0.35,  # donut style
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        return fig

    def _heatmap(self, df: pd.DataFrame, spec: dict) -> go.Figure:
        # Pivot: rows = x_col, cols = group_by, values = y metric
        x_col     = df.columns[0]
        y_cols    = [c.lower() for c in spec["y_axis"]["columns"]
                     if c.lower() in df.columns]
        group     = spec.get("group_by", "").lower() if spec.get("group_by") else None
        val_col   = y_cols[0] if y_cols else df.columns[-1]

        if group and group in df.columns:
            pivot = df.pivot_table(
                index=x_col, columns=group,
                values=val_col, aggfunc="sum"
            ).fillna(0)
            fig = px.imshow(
                pivot, color_continuous_scale="RdYlGn",
                aspect="auto",
            )
        else:
            # Fallback: simple bar if can't pivot
            fig = self._bar_chart(df, spec)
        return fig

    def _treemap(self, df: pd.DataFrame, spec: dict) -> go.Figure:
        x_col  = df.columns[0]
        y_cols = [c.lower() for c in spec["y_axis"]["columns"]
                  if c.lower() in df.columns]
        val    = y_cols[0] if y_cols else df.columns[1]
        df     = df[df[val] > 0]  # treemap can't handle negatives

        fig = px.treemap(
            df, path=[x_col], values=val,
            color=val,
            color_continuous_scale="Blues",
        )
        return fig

    def _stacked_bar(self, df: pd.DataFrame, spec: dict) -> go.Figure:
        x_col  = df.columns[0]
        y_cols = [c.lower() for c in spec["y_axis"]["columns"]
                  if c.lower() in df.columns]
        group  = spec.get("group_by", "").lower() if spec.get("group_by") else None

        if group and group in df.columns:
            y_col = y_cols[0] if y_cols else df.columns[-1]
            fig   = px.bar(
                df, x=x_col, y=y_col, color=group,
                barmode="stack",
                color_discrete_sequence=COLOR_SEQ,
            )
        else:
            df_melt = df.melt(id_vars=[x_col], value_vars=y_cols,
                              var_name="metric", value_name="value")
            fig = px.bar(
                df_melt, x=x_col, y="value", color="metric",
                barmode="stack",
                color_discrete_sequence=COLOR_SEQ,
            )
        fig.update_layout(xaxis_tickangle=-35)
        return fig

    # ─────────────────────────────────────────────
    # Styling helpers
    # ─────────────────────────────────────────────
    def _apply_theme(self, fig: go.Figure, spec: dict) -> go.Figure:
        fig.update_layout(
            template=PLOTLY_THEME,
            title={
                "text":  spec.get("title", ""),
                "x":     0.04,
                "font":  {"size": 15, "color": "#1a1a2e"},
            },
            margin=dict(t=52, l=12, r=12, b=48),
            legend=dict(orientation="h", yanchor="bottom",
                        y=1.02, xanchor="right", x=1),
            xaxis_title=spec.get("x_axis", {}).get("label", ""),
            yaxis_title=spec.get("y_axis", {}).get("label", ""),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", size=12),
        )
        return fig

    def _empty_figure(self, title: str) -> go.Figure:
        fig = go.Figure()
        fig.add_annotation(
            text="No data returned for this query",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#888"),
        )
        fig.update_layout(title=title, template=PLOTLY_THEME)
        return fig