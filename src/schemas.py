# Pydantic models for data validation and API typing
from pydantic import BaseModel, Field
from typing import List

# ==============================================================================
# FastAPI Endpoint Schemas (API Layer)
# ==============================================================================

class ChatRequest(BaseModel):
    """Schema for incoming chat requests to the FastAPI backend."""
    query: str = Field(
        ..., 
        description="The user's financial query or prompt for the analyst agent.",
        min_length=1,
        example="Prepare a quarterly briefing for Client CLT-001."
    )

class ChatResponse(BaseModel):
    """Schema for outgoing chat responses from the FastAPI backend."""
    response: str = Field(
        ..., 
        description="The agent's final text response formatted in Markdown."
    )
    tools_used: List[str] = Field(
        default_factory=list, 
        description="A list of tool names the agent utilized to answer the query."
    )


# ==============================================================================
# Agent Tool Schemas (LangChain Layer)
# ==============================================================================
# Note: You can bind these to your tools in agents.py using @tool(args_schema=...)
# to enforce strict typing on the LLM's tool calls.

class PortfolioLookupSchema(BaseModel):
    """Input schema for the portfolio_lookup tool."""
    client_id: str = Field(
        ..., 
        description="The unique client ID to look up (e.g., 'CLT-001', 'CLT-002'). Must include the 'CLT-' prefix."
    )

class MarketDataSearchSchema(BaseModel):
    """Input schema for the market_data_search tool."""
    query: str = Field(
        ..., 
        description="A stock ticker (e.g., 'RELIANCE'), sector name (e.g., 'IT', 'Banking'), or company name."
    )

class CalculateMetricsSchema(BaseModel):
    """Input schema for the calculate_metrics tool."""
    expression: str = Field(
        ..., 
        description="Describe the calculation in natural language, including the numbers. "
                    "Examples: 'return on 596000 vs cost 430000', 'percentage of 350000 out of 2530000', "
                    "or 'compare 18.5 vs 12.3'."
    )

class PolicyRetrieverSchema(BaseModel):
    """Input schema for the policy_retriever tool."""
    query: str = Field(
        ..., 
        description="A natural language query about investment policies, risk limits, "
                    "rebalancing thresholds, or suitability standards to search within the vector database."
    )