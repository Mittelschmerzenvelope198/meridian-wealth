# ReAct agent definition and tool wrappers
import json
import re
import os
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langchain.agents import create_agent

from src.config import CONFIG
from src.database_queries import get_client_portfolio, search_market_data, query_db
from src.rag_pipeline import policy_retriever_chain

# Import the Pydantic schemas to strictly enforce tool arguments
from src.schemas import (
    PortfolioLookupSchema,
    MarketDataSearchSchema,
    CalculateMetricsSchema,
    PolicyRetrieverSchema
)

# ------------------------------------------------------------------------------
# Tool Definitions
# ------------------------------------------------------------------------------

@tool(args_schema=PortfolioLookupSchema)
def portfolio_lookup(client_id: str) -> str:
    """Look up a client's portfolio from the database: holdings, allocation, total value, and risk profile.
    Use this when you need to know what a specific client owns or their investment profile.
    Input: client ID like 'CLT-001', 'CLT-002', etc."""
    portfolio = get_client_portfolio(client_id.upper())
    if not portfolio:
        available = [r["client_id"] for r in query_db("SELECT client_id FROM clients")]
        return f"Client {client_id} not found. Available: {', '.join(available)}"

    c = portfolio["client"]
    holdings = portfolio["holdings"]

    total_current = sum(h["shares"] * h["current_price"] for h in holdings)
    total_cost = sum(h["shares"] * h["avg_cost_basis"] for h in holdings)
    overall_return = ((total_current - total_cost) / total_cost) * 100 if total_cost else 0

    # Sector allocation
    sector_values = {}
    for h in holdings:
        val = h["shares"] * h["current_price"]
        sector_values[h["sector"]] = sector_values.get(h["sector"], 0) + val
    sector_pct = {s: round((v / total_current) * 100, 1) for s, v in sector_values.items()}

    # Per-holding detail
    holdings_detail = []
    for h in holdings:
        cv = h["shares"] * h["current_price"]
        gain = ((h["current_price"] - h["avg_cost_basis"]) / h["avg_cost_basis"]) * 100
        wt = (cv / total_current) * 100
        holdings_detail.append({
            "ticker": h["ticker"], "company": h["company_name"],
            "shares": h["shares"], "avg_cost": h["avg_cost_basis"],
            "current_price": h["current_price"], "current_value": cv,
            "unrealized_gain_pct": round(gain, 1), "portfolio_weight_pct": round(wt, 1),
            "sector": h["sector"], "ytd_return": h["ytd_return_pct"],
            "analyst_rating": h["analyst_rating"], "purchase_date": h["purchase_date"]
        })

    result = {
        "client_id": c["client_id"], "name": c["name"],
        "relationship_manager": c["relationship_mgr"], "risk_profile": c["risk_profile"],
        "investment_horizon": c["investment_horizon"], "aum_inr": c["aum_inr"],
        "last_review": c["last_review"],
        "total_portfolio_value": round(total_current),
        "total_cost_basis": round(total_cost),
        "overall_return_pct": round(overall_return, 1),
        "sector_allocation": sector_pct,
        "holdings": holdings_detail
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@tool(args_schema=MarketDataSearchSchema)
def market_data_search(query: str) -> str:
    """Search the market database for stock tickers or sectors. Returns current price, YTD returns,
    PE ratio, analyst ratings, 52-week range, and market cap. Use this when you need market
    performance data for specific stocks or want to compare sector performance.
    Input: a stock ticker (e.g. 'RELIANCE'), sector name (e.g. 'IT', 'Banking'), or company name."""
    results = search_market_data(query)
    if not results:
        all_tickers = [r["ticker"] for r in query_db("SELECT ticker FROM market_data")]
        return f"No data found for '{query}'. Available: {', '.join(all_tickers)}"

    formatted = [{
        "ticker": r["ticker"], "company": r["company_name"], "sector": r["sector"],
        "price": r["current_price"], "ytd_return": r["ytd_return_pct"],
        "pe_ratio": r["pe_ratio"], "analyst_rating": r["analyst_rating"],
        "52w_range": f"{r['low_52w']} - {r['high_52w']}",
        "market_cap_cr": r["market_cap_cr"]
    } for r in results]
    return json.dumps(formatted, indent=2, ensure_ascii=False)


@tool(args_schema=CalculateMetricsSchema)
def calculate_metrics(expression: str) -> str:
    """Perform financial calculations: returns, percentages, allocations, comparisons.
    Input: describe the calculation, e.g. 'return on 596000 vs cost 430000'
    or 'percentage of 350000 out of 2530000' or 'compare 18.5 vs 12.3'."""
    try:
        numbers = [float(x.replace(',', '')) for x in re.findall(r'[\d,]+\.?\d*', expression)]

        if "return" in expression.lower() or "gain" in expression.lower():
            if len(numbers) >= 2:
                current, cost = numbers[0], numbers[1]
                ret = ((current - cost) / cost) * 100
                return f"Return: (₹{current:,.0f} - ₹{cost:,.0f}) / ₹{cost:,.0f} = {ret:+.2f}%"

        if "percentage" in expression.lower() or "allocation" in expression.lower() or "weight" in expression.lower():
            if len(numbers) >= 2:
                part, whole = numbers[0], numbers[1]
                return f"Percentage: ₹{part:,.0f} / ₹{whole:,.0f} = {(part/whole)*100:.2f}%"

        if "compare" in expression.lower() and len(numbers) >= 2:
            a, b = numbers[0], numbers[1]
            return f"Comparison: {a:,.2f} vs {b:,.2f} | Diff: {a-b:+,.2f} ({((a-b)/b)*100:+.2f}%)"

        if len(numbers) == 2:
            a, b = numbers
            return f"Values: {a:,.2f} and {b:,.2f} | Sum: {a+b:,.2f} | Diff: {a-b:+,.2f} | Ratio: {a/b:.4f}"

        return f"Values parsed: {numbers}. Please verify operation parameters."
    except Exception as e:
        return f"Calculation error: {str(e)}"


@tool(args_schema=PolicyRetrieverSchema)
def policy_retriever(query: str) -> str:
    """Search Meridian Wealth Partners' investment policy PDF documents using RAG (vector similarity search).
    Use this when you need to check investment guidelines, allocation rules, rebalancing triggers,
    risk limits, concentration limits, suitability standards, or reporting requirements.
    Returns relevant excerpts with source document name and page number.
    Input: a natural language query about investment policies."""
    docs = policy_retriever_chain.invoke(query)
    results = []
    for i, doc in enumerate(docs, 1):
        src = os.path.basename(doc.metadata.get("source", "unknown"))
        pg = doc.metadata.get("page", "?")
        results.append(f"[Policy Doc {i}: {src} | Page {pg}]\n{doc.page_content}")
    return "\n\n---\n\n".join(results)


# Initialize live web search tool using config settings
web_search = TavilySearch(
    max_results=CONFIG['tools']['tavily_search']['max_results'], 
    topic=CONFIG['tools']['tavily_search']['topic']
)

# ------------------------------------------------------------------------------
# Agent Initialization
# ------------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a senior financial analyst at Meridian Wealth Partners, a SEBI-registered wealth
management firm managing ₹2,000 Crore in assets across 800 high-net-worth Indian clients.

Your job is to prepare comprehensive client briefings and answer investment queries using your tools.

AVAILABLE DATA SOURCES:
1. portfolio_lookup — queries the SQL database for client holdings, allocation, and risk profile
2. market_data_search — queries the SQL database for stock/sector data (price, YTD, PE, analyst ratings)
3. calculate_metrics — computes financial metrics (returns, allocation percentages, comparisons)
4. policy_retriever — RAG search over the firm's 5 investment policy PDFs (asset allocation, risk management,
   suitability standards, rebalancing protocol, reporting standards)
5. tavily_search — searches the web for latest market news, RBI updates, sector analysis

GUIDELINES:
- Always check the client's risk profile before making recommendations
- When checking policy compliance, ALWAYS use the policy_retriever tool — never guess the rules
- Cite specific policy document names and page numbers when referencing guidelines
- Do not provide compliance conclusions without first using policy_retriever.
- Do not provide market-news claims without using tavily_search.
- If required data is missing, say so explicitly instead of inferring.
- Use Indian Rupee (₹) for all amounts. Use lakhs and crores for large values.
- Include specific numbers: exact returns, allocation percentages, policy thresholds
- For briefings, structure as: Portfolio Summary → Market Context → Policy Compliance → Recommendations
"""

tools = [portfolio_lookup, market_data_search, calculate_metrics, policy_retriever, web_search]

# Initialize LLM without temperature setting as per revised config
llm = ChatOpenAI(
    model=CONFIG['llm']['model_name']
)

# Uses the modern LangChain v1 create_agent harness as specified
agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT
)