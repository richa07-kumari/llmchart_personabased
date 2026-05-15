import streamlit as st
from layer1.schema_store        import SchemaStore
from layer1.snowflake_connector import SnowflakeConnector
from layer2.persona_registry    import PersonaRegistry
from layer2.persona_engine      import PersonaEngine
from layer2.insight_planner     import InsightPlanner
from layer2.sql_generator       import SQLGenerator
from layer3.dashboard_layout    import render_dashboard

st.set_page_config(
    page_title="AI Dashboard",
    page_icon="chart_with_upwards_trend",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────
with st.sidebar:
    st.markdown("## AI Persona Dashboard")
    st.markdown("Select a business role to generate personalised insights.")
    st.markdown("---")

    PERSONA_LABELS = {
        "ceo":                  "CEO / Managing Director",
        "sales_officer":        "Sales Officer",
        "cfo":                  "CFO / Finance Director",
        "supply_chain_manager": "Supply Chain Manager",
        "marketing_manager":    "Marketing Manager",
    }

    selected_key = st.selectbox(
        "Select persona",
        options=list(PERSONA_LABELS.keys()),
        format_func=lambda k: PERSONA_LABELS[k],
    )

    run_btn = st.button("Generate Dashboard", type="primary", use_container_width=True)

    st.markdown("---")
    st.markdown(
        "<small style='color:#888'>Powered by Claude + Snowflake</small>",
        unsafe_allow_html=True,
    )

# ── Session state ─────────────────────────────────
if "results"       not in st.session_state:
    st.session_state.results       = []
if "active_persona" not in st.session_state:
    st.session_state.active_persona = None

# ── Pipeline execution ────────────────────────────
@st.cache_resource
def load_layer1():
    """Load schema and connector once per Streamlit session."""
    schema = SchemaStore().load()
    sf     = SnowflakeConnector()
    return schema, sf

if run_btn or (st.session_state.active_persona != selected_key
               and st.session_state.results):
    schema, sf = load_layer1()

    with st.spinner(f"Generating insights for {PERSONA_LABELS[selected_key]}..."):
        try:
            registry = PersonaRegistry()
            engine   = PersonaEngine(schema=schema, registry=registry)
            planner  = InsightPlanner(schema=schema)
            sqlgen   = SQLGenerator(connector=sf)

            print(f"\n[App] ========== PIPELINE START ==========")
            print(f"[App] Persona: {selected_key}")
            
            # Step 1: Generate questions
            print(f"[App] Step 1: Generating business questions...")
            questions   = engine.generate(selected_key)
            print(f"[App] ✓ Generated {len(questions)} questions")
            for i, q in enumerate(questions[:2], 1):
                print(f"     Q{i}: {q['question'][:60]}")
            
            if not questions:
                st.error("❌ No questions generated from PersonaEngine")
                print(f"[App] ERROR: Questions list is empty!")
            else:
                # Step 2: Plan charts
                print(f"[App] Step 2: Planning chart specifications...")
                chart_specs = planner.plan(questions)
                print(f"[App] ✓ Generated {len(chart_specs)} chart specs")
                for i, spec in enumerate(chart_specs[:2], 1):
                    print(f"     S{i}: {spec.get('title', 'N/A')[:50]} ({spec.get('chart_type')})")
                
                if not chart_specs:
                    st.error("❌ No chart specs generated from InsightPlanner")
                    print(f"[App] ERROR: Chart specs list is empty!")
                else:
                    # Step 3: Execute queries
                    print(f"[App] Step 3: Executing SQL queries...")
                    results     = sqlgen.execute_all(chart_specs)
                    print(f"[App] ✓ Generated {len(results)} results")
                    
                    if not results:
                        st.error("❌ No results returned from SQLGenerator")
                        print(f"[App] ERROR: Results list is empty!")
                    else:
                        st.session_state.results        = results
                        st.session_state.active_persona = selected_key
                        st.success(f"✅ Generated {len(results)} insights!")
                        print(f"[App] ========== PIPELINE SUCCESS ==========\n")
            
        except Exception as e:
            st.error(f"❌ Pipeline Error: {str(e)}")
            print(f"[App] EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            print(f"[App] ========== PIPELINE FAILED ==========\n")

# ── Main content ──────────────────────────────────
if st.session_state.results:
    print(f"[App] Rendering dashboard with {len(st.session_state.results)} results")
    print(f"[App] Results type: {type(st.session_state.results)}")
    print(f"[App] First result type: {type(st.session_state.results[0]) if st.session_state.results else 'N/A'}")
    if st.session_state.results and isinstance(st.session_state.results[0], dict):
        print(f"[App] First result keys: {st.session_state.results[0].keys()}")
        render_dashboard(
        persona_name=PERSONA_LABELS[st.session_state.active_persona],
        results=st.session_state.results,
    )
else:
    # Landing state
    st.markdown(
        """
        <div style="text-align:center; padding:80px 20px; color:#888">
            <div style="font-size:48px; margin-bottom:16px">chart_with_upwards_trend</div>
            <h2 style="color:#444">Select a persona and click Generate Dashboard</h2>
            <p>The AI will analyse the Superstore dataset and build<br>
               personalised charts based on your role.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )