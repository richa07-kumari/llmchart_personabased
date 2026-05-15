import streamlit as st
import pandas as pd
from layer3.chart_renderer  import ChartRenderer
from layer3.narrative_engine import NarrativeEngine

renderer  = ChartRenderer()
narrator  = NarrativeEngine()

PRIORITY_COLORS = {
    "high":   "#E05C5C",
    "medium": "#F0A500",
    "low":    "#4C9BE8",
}


def render_chart_card(result: dict, col) -> None:
    """Renders one chart as a Streamlit card inside a given column (or st for full-width)."""
    priority = result.get("priority", "medium")
    color    = PRIORITY_COLORS.get(priority, "#888")
    title    = result.get("title", "Chart")

    # Check if col is a Streamlit container (has __enter__ method) or just st module
    if hasattr(col, '__enter__'):
        # It's a column object - use context manager
        container = col
    else:
        # It's the st module - create a simple context-like wrapper
        class StWrapper:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        container = StWrapper()
    
    with container:
        # Priority badge + title
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px">
              <span style="background:{color}; color:white; font-size:11px;
                           padding:2px 8px; border-radius:10px; font-weight:600">
                {priority.upper()}
              </span>
              <span style="font-size:15px; font-weight:600; color:#1a1a2e">{title}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Plotly chart
        fig = renderer.render(result)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # LLM narrative insight
        with st.spinner("Generating insight..."):
            narrative = narrator.generate(result)

        st.markdown(
            f"""
            <div style="background:#F0F4FF; border-left:3px solid {color};
                        padding:8px 12px; border-radius:0 6px 6px 0;
                        font-size:13px; color:#333; margin-top:-8px">
              {narrative}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Expandable raw data table
        with st.expander("View data"):
            st.dataframe(result["dataframe"], use_container_width=True)


def render_dashboard(persona_name: str, results: list[dict]) -> None:
    """
    Renders the full dashboard for a persona.
    High priority charts get full width; medium and low share two columns.
    """
    if not results:
        st.warning("No charts generated. Try a different persona.")
        return

    # Validate all results are dicts
    print(f"[Dashboard] Validating {len(results)} results...")
    valid_results = []
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            st.error(f"❌ Result {i+1} is {type(r).__name__}, not a dict!")
            print(f"[Dashboard] ERROR: Result {i} is {type(r)}, skipping. Value: {r}")
            continue
        valid_results.append(r)
    
    if not valid_results:
        st.error("❌ No valid results to display (all results were invalid)")
        return
    
    results = valid_results

    st.markdown(
        f"""
        <h2 style="color:#1a1a2e; margin-bottom:2px">
            {persona_name} Dashboard
        </h2>
        <p style="color:#666; font-size:13px; margin-top:0">
            {len(results)} insights generated from Superstore dataset
        </p>
        <hr style="border:none; border-top:1px solid #eee; margin:12px 0 20px">
        """,
        unsafe_allow_html=True,
    )

    high   = [r for r in results if r.get("priority") == "high"]
    medium = [r for r in results if r.get("priority") == "medium"]
    low    = [r for r in results if r.get("priority") == "low"]

    # High priority — full width, one per row
    if high:
        st.markdown("#### Key metrics")
        for result in high:
            render_chart_card(result, st)
            st.markdown("<div style='margin-bottom:20px'></div>",
                        unsafe_allow_html=True)

    # Medium priority — two columns
    if medium:
        st.markdown("#### Supporting analysis")
        cols = st.columns(2)
        for i, result in enumerate(medium):
            render_chart_card(result, cols[i % 2])

    # Low priority — two columns
    if low:
        st.markdown("#### Additional context")
        cols = st.columns(2)
        for i, result in enumerate(low):
            render_chart_card(result, cols[i % 2])