from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PersonaConfig:
    """
    Defines the business context for a single role/persona.
    All fields feed directly into the Part 2 LLM system prompt.
    """
    role:               str
    display_name:       str
    description:        str
    core_kpis:          list[str]
    business_questions: list[str]
    preferred_charts:   list[str]
    time_horizon:       str
    decision_context:   str
    avoid_metrics:      list[str] = field(default_factory=list)


class PersonaRegistry:
    """
    Central store of all supported personas.
    Call get(role_name) to retrieve a PersonaConfig.
    Call list_roles() to see all supported role names.
    """

    _PERSONAS: dict[str, PersonaConfig] = {

        "ceo": PersonaConfig(
            role="ceo",
            display_name="CEO / Managing Director",
            description=(
                "Responsible for overall business performance and strategic direction. "
                "Needs high-level trends, not operational detail."
            ),
            core_kpis=[
                "Total revenue (SALES)",
                "Total profit (PROFIT)",
                "Profit margin % (PROFIT / SALES)",
                "Year-over-year growth",
                "Revenue by region (REGION)",
                "Revenue by category (CATEGORY)",
            ],
            business_questions=[
                "How is overall revenue trending month by month?",
                "Which product categories are driving the most profit?",
                "Which regions are underperforming on profit margin?",
                "What is the profit margin breakdown by customer segment?",
                "How do discounts affect overall profitability?",
            ],
            preferred_charts=[
                "line chart",
                "bar chart",
                "treemap",
                "KPI scorecard",
            ],
            time_horizon="monthly and yearly trends",
            decision_context=(
                "Strategic: looking for patterns and anomalies to guide "
                "resource allocation and business priorities."
            ),
            avoid_metrics=[
                "individual order details",
                "postal codes",
                "ship mode breakdown",
            ],
        ),

        "sales_officer": PersonaConfig(
            role="sales_officer",
            display_name="Sales Officer / Sales Manager",
            description=(
                "Responsible for sales pipeline, revenue targets, and "
                "customer acquisition. Needs operational sales metrics."
            ),
            core_kpis=[
                "Total sales (SALES) by region and state",
                "Sales by customer segment (SEGMENT)",
                "Top performing products (PRODUCT_NAME)",
                "Sales by sub-category (SUB_CATEGORY)",
                "Order volume (COUNT of ORDER_ID)",
                "Average order value (AVG of SALES)",
            ],
            business_questions=[
                "Which states and cities have the highest sales volume?",
                "Which customer segments (Consumer, Corporate, Home Office) buy the most?",
                "What are the top 10 products by revenue?",
                "How does sales volume vary by ship mode?",
                "What is the monthly sales trend over the dataset period?",
                "Which sub-categories are gaining or losing sales momentum?",
            ],
            preferred_charts=[
                "bar chart",
                "ranked horizontal bar",
                "line chart",
                "map / choropleth",
            ],
            time_horizon="monthly and quarterly",
            decision_context=(
                "Operational: identifying which regions, customers, and products "
                "to prioritise for sales effort and targets."
            ),
            avoid_metrics=[
                "profit margin internals",
                "cost breakdowns",
            ],
        ),

        "cfo": PersonaConfig(
            role="cfo",
            display_name="CFO / Finance Director",
            description=(
                "Responsible for financial health, cost control, and profitability. "
                "Needs granular profit, discount, and cost analysis."
            ),
            core_kpis=[
                "Profit margin by category and sub-category",
                "Impact of discount on profit (DISCOUNT vs PROFIT correlation)",
                "Loss-making orders (orders where PROFIT < 0)",
                "Total profit by region",
                "Profit trend over time",
                "High-discount low-profit segments",
            ],
            business_questions=[
                "Which product sub-categories are consistently loss-making?",
                "What is the relationship between discount level and profit?",
                "Which regions have the lowest profit margins?",
                "How many orders result in a loss, and what drives that?",
                "What is the profit trend across order dates?",
                "Which customer segments are most and least profitable?",
            ],
            preferred_charts=[
                "scatter plot",
                "bar chart",
                "line chart",
                "heatmap",
            ],
            time_horizon="quarterly and annual",
            decision_context=(
                "Financial control: identifying cost leakage, discount abuse, "
                "and unprofitable segments to improve margins."
            ),
            avoid_metrics=[
                "raw order counts without profit context",
                "ship mode",
            ],
        ),

        "supply_chain_manager": PersonaConfig(
            role="supply_chain_manager",
            display_name="Supply Chain / Operations Manager",
            description=(
                "Responsible for logistics, fulfilment, and delivery performance. "
                "Needs shipping and order fulfilment data."
            ),
            core_kpis=[
                "Orders by ship mode (SHIP_MODE)",
                "Average days to ship (SHIP_DATE - ORDER_DATE)",
                "Order volume by region and state",
                "Quantity ordered by category (QUANTITY)",
                "Orders per month (ORDER_DATE trend)",
            ],
            business_questions=[
                "What is the distribution of orders across ship modes?",
                "Which regions have the highest order volumes to fulfil?",
                "How does order volume vary seasonally across months?",
                "Which categories require the largest quantities shipped?",
                "Are there patterns in ship mode usage by customer segment?",
            ],
            preferred_charts=[
                "bar chart",
                "pie chart",
                "line chart",
                "stacked bar",
            ],
            time_horizon="weekly and monthly",
            decision_context=(
                "Operational: optimising fulfilment routes, warehouse stock, "
                "and shipping partner allocation."
            ),
            avoid_metrics=[
                "profit",
                "discount details",
                "individual customer names",
            ],
        ),

        "marketing_manager": PersonaConfig(
            role="marketing_manager",
            display_name="Marketing Manager",
            description=(
                "Responsible for customer acquisition, segment performance, and "
                "campaign ROI. Needs customer and product mix data."
            ),
            core_kpis=[
                "Sales by customer segment (SEGMENT)",
                "Top products by sales volume",
                "Category and sub-category mix",
                "Geographic spread (STATE, CITY, REGION)",
                "New vs repeat customers (CUSTOMER_NAME frequency)",
                "Discount effectiveness (DISCOUNT vs SALES)",
            ],
            business_questions=[
                "Which customer segments drive the most revenue?",
                "Which product categories are growing in sales?",
                "Which cities and states represent untapped sales potential?",
                "Are high-discount promotions driving incremental sales?",
                "What is the product mix within each customer segment?",
            ],
            preferred_charts=[
                "bar chart",
                "pie chart",
                "bubble chart",
                "line chart",
            ],
            time_horizon="monthly and quarterly",
            decision_context=(
                "Strategic marketing: identifying high-value segments and "
                "regions for targeted campaigns and promotions."
            ),
            avoid_metrics=[
                "ship mode",
                "postal code",
                "loss-making orders",
            ],
        ),
    }

    def get(self, role: str) -> PersonaConfig:
        """
        Retrieve a PersonaConfig by role name (case-insensitive).
        Raises ValueError for unknown roles.
        """
        key = role.lower().strip().replace(" ", "_")
        if key not in self._PERSONAS:
            available = ", ".join(self._PERSONAS.keys())
            raise ValueError(
                f"Unknown persona '{role}'. "
                f"Available roles: {available}"
            )
        return self._PERSONAS[key]

    def list_roles(self) -> list[str]:
        """Returns all supported role names."""
        return list(self._PERSONAS.keys())

    def get_all(self) -> list[PersonaConfig]:
        """Returns all PersonaConfig objects."""
        return list(self._PERSONAS.values())

    def to_llm_context(self, role: str) -> str:
        """
        Formats a PersonaConfig as a compact string block
        ready to be injected into a Layer 2 LLM system prompt.
        """
        p = self.get(role)
        lines = [
            f"PERSONA: {p.display_name}",
            f"DESCRIPTION: {p.description}",
            f"TIME HORIZON: {p.time_horizon}",
            f"DECISION CONTEXT: {p.decision_context}",
            "",
            "CORE KPIs:",
            *[f"  - {kpi}" for kpi in p.core_kpis],
            "",
            "KEY BUSINESS QUESTIONS:",
            *[f"  - {q}" for q in p.business_questions],
            "",
            "PREFERRED CHART TYPES:",
            *[f"  - {c}" for c in p.preferred_charts],
            "",
            "AVOID THESE METRICS:",
            *[f"  - {m}" for m in p.avoid_metrics],
        ]
        return "\n".join(lines)