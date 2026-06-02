# Architecture Overview: Meridian Financial Analyst Agent

This document details the system architecture, data flow, and design principles of the Meridian Wealth Partners Financial Analyst Agentic Web App.

## System Design

The application is built using a modern, decoupled architecture centered around FastAPI for the backend and LangChain/LangGraph for the agentic orchestration. The design explicitly separates concerns across configuration, data access, unstructured retrieval, and agent logic.

### Core Architectural Layers

1.  **Presentation Layer (Frontend):**
    * **Technology:** HTML, CSS, JavaScript (Vanilla), Jinja2 Templating.
    * **Role:** Provides the user interfaces (`/`, `/chat`, `/agent_info`). The frontend is served by FastAPI and interacts asynchronously with the backend via REST API calls (AJAX/Fetch) to the `/api/chat` endpoint.

2.  **API Routing Layer (FastAPI Backend):**
    * **Technology:** FastAPI (`app.py`), Uvicorn.
    * **Role:** Acts as the entry point. It manages HTTP requests, handles static file serving, renders Jinja2 templates, and defines API endpoints. It includes a comprehensive `/health` endpoint that checks system integrity (DB presence, API keys, Vector DB status) before serving requests.

3.  **Agent Orchestration Layer:**
    * **Technology:** LangChain v1 (`create_agent`), OpenAI GPT-4o-mini (`ChatOpenAI`).
    * **Role:** The core "brain" located in `src/agents.py`. It utilizes a ReAct (Reasoning and Acting) loop to determine which tools to call, parse the observations, and synthesize the final answer based on a strict `SYSTEM_PROMPT`.

4.  **Tooling & Data Access Layer:**
    * **Technology:** Python, SQLite, FAISS, LangChain Tools, Pydantic.
    * **Role:** The specific capabilities granted to the agent, heavily typed using Pydantic schemas (`src/schemas.py`) to enforce reliable LLM tool-calling.

## Data Infrastructure

The agent interacts with three distinct data modalities, mirroring enterprise wealth management systems:

### 1. Structured Data (SQL Database)
* **Source:** `data/meridian_wealth.db` (SQLite)
* **Module:** `src/database_queries.py`
* **Description:** A relational database containing 3 normalized tables: `clients`, `holdings`, and `market_data`.
* **Tools Used:** * `portfolio_lookup`: Joins client profiles with their specific holdings and enriches them with current market prices.
    * `market_data_search`: Queries specific ticker or sector performance metrics.

### 2. Unstructured Data (Vector RAG Pipeline)
* **Source:** `data/policy_documents/*.pdf` -> `vectordb/meridian_vector_db.faiss`
* **Module:** `src/rag_pipeline.py`
* **Description:** Firm policies regarding asset allocation, risk limits, and rebalancing protocols.
* **Workflow:**
    1.  **Ingestion:** `PyPDFLoader` extracts text from the 5 policy documents.
    2.  **Chunking:** `RecursiveCharacterTextSplitter` breaks text into chunks (Size: 1000, Overlap: 300) for context preservation.
    3.  **Embedding:** Chunks are vectorized using OpenAI's `text-embedding-3-small`.
    4.  **Storage:** Vectors are indexed using FAISS and serialized to the `/vectordb` directory for persistence across server restarts.
    5.  **Retrieval:** The `policy_retriever` tool performs a similarity search, returning the top *k* (4) most relevant chunks with source citations.

### 3. Real-Time Data (Live Web Search)
* **Source:** Tavily API
* **Module:** `src/agents.py`
* **Description:** Provides the agent with current market news, central bank (RBI) updates, and sector analysis that cannot exist in static databases.
* **Tools Used:** `tavily_search` configured to focus on "news" topics.

## Configuration Management

* **Module:** `src/config.py` & `config.yaml`
* **Design Principle:** "Configuration over Code".
* All dynamic parameters—such as LLM model selection, text splitting chunk sizes, vector DB naming, and tool constraints (e.g., max search results)—are decoupled from the Python code and managed entirely within `config.yaml`. The `config.py` script loads this YAML, resolves absolute paths dynamically, and exposes a global `CONFIG` object imported by all other modules.

## ReAct Agent Execution Flow

1.  **User Request:** The user submits a natural language query via the `/chat` UI.
2.  **Endpoint:** The frontend sends a POST request to `/api/chat`, validated by the `ChatRequest` Pydantic schema.
3.  **Agent Invocation:** `app.py` passes the input to the compiled LangChain agent.
4.  **ReAct Loop:** * **Thought:** The LLM analyzes the query against its `SYSTEM_PROMPT` constraints.
    * **Action:** It selects one or more tools (e.g., `portfolio_lookup("CLT-001")`, then `policy_retriever("Sector concentration limits")`).
    * **Observation:** The tools execute against the SQLite DB or FAISS index and return JSON strings or formatted text.
    * *The agent repeats this loop until it has sufficient information to formulate a comprehensive answer.*
5.  **Final Response:** The agent synthesizes the observations into a structured response (Summary -> Market Context -> Policy Compliance -> Recommendations).
6.  **API Return:** The `/api/chat` endpoint returns the text response and a list of the specific tools utilized during the execution to the frontend.
