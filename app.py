# FastAPI application entry point and routing
import os
import json
import asyncio
import sqlite3
import threading
from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import CONFIG
from src.schemas import ChatRequest, ChatResponse
from src.agents import agent, tools as AGENT_TOOLS
from src.database_queries import query_db

# Initialize FastAPI Application
app = FastAPI(
    title=CONFIG['app']['name'],
    version=CONFIG['app']['version']
)

# Setup directories for Static Assets and HTML Views
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))

# Mount static files directory (for custom CSS/JS assets)
static_dir = os.path.join(BASE_DIR, "frontend", "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ==============================================================================
# Tool & Data Source Metadata
# ==============================================================================
# Supplementary display metadata keyed by each tool's registered name. The
# human-readable description is pulled live from the tool definitions in
# src/agents.py so this page can never drift from the actual agent behaviour.
_TOOL_META = {
    "portfolio_lookup": {
        "label": "Portfolio Lookup",
        "source": "SQLite — clients + holdings tables",
        "input": "A client ID such as 'CLT-001'",
        "data_view": "portfolio",
    },
    "market_data_search": {
        "label": "Market Data Search",
        "source": "SQLite — market_data table",
        "input": "A ticker ('RELIANCE'), sector ('IT'), or company name",
        "data_view": "market",
    },
    "calculate_metrics": {
        "label": "Calculate Metrics",
        "source": "In-process financial computation (no external data)",
        "input": "A natural-language calculation, e.g. 'return on 596000 vs cost 430000'",
        "data_view": None,
    },
    "policy_retriever": {
        "label": "Policy Retriever (RAG)",
        "source": "FAISS vector store over the firm's policy PDFs",
        "input": "A natural-language policy question",
        "data_view": "policy",
    },
    "tavily_search": {
        "label": "Web Search (Tavily)",
        "source": "Live web via the Tavily Search API",
        "input": "A market-news or research query",
        "data_view": "intelligence",
    },
}


def get_tools_info():
    """Builds the detailed tool catalogue (name, purpose, data source, input)."""
    info = []
    for t in AGENT_TOOLS:
        meta = _TOOL_META.get(t.name, {})
        info.append({
            "name": t.name,
            "label": meta.get("label", t.name),
            "description": " ".join((t.description or "").split()),
            "source": meta.get("source", "—"),
            "input": meta.get("input", "—"),
            "data_view": meta.get("data_view"),
        })
    return info


def public_config():
    """Returns the config without filesystem paths (internal deployment detail)."""
    return {k: v for k, v in CONFIG.items() if k != "paths"}


def list_policy_documents():
    """Lists the policy PDFs backing the RAG pipeline, with size and page count."""
    policy_dir = CONFIG['paths']['policy_documents_dir']
    docs = []
    if not os.path.isdir(policy_dir):
        return docs
    for fname in sorted(f for f in os.listdir(policy_dir) if f.lower().endswith(".pdf")):
        fpath = os.path.join(policy_dir, fname)
        entry = {
            "name": fname,
            "title": os.path.splitext(fname)[0].replace("_", " "),
            "size_kb": round(os.path.getsize(fpath) / 1024, 1),
            "pages": None,
        }
        try:
            from pypdf import PdfReader
            entry["pages"] = len(PdfReader(fpath).pages)
        except Exception:
            pass
        docs.append(entry)
    return docs


# ==============================================================================
# HTML Interface Endpoints
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the main landing page (index.html) of the application."""
    return templates.TemplateResponse(request, "index.html", {"app_name": CONFIG['app']['name']})


@app.get("/chat", response_class=HTMLResponse)
async def read_chat(request: Request):
    """Serves the primary conversational workspace UI (chat.html)."""
    return templates.TemplateResponse(request, "chat.html", {"app_name": CONFIG['app']['name']})


@app.get("/agent_info", response_class=HTMLResponse)
async def read_agent_info(request: Request):
    """Emits and visualizes the structured system parameters extracted from config.yaml."""
    return templates.TemplateResponse(
        request,
        "agent_info.html",
        {
            "app_name": CONFIG['app']['name'],
            "config_data": public_config(),
            "tools_info": get_tools_info()
        }
    )


@app.get("/data", response_class=HTMLResponse)
async def read_data(request: Request):
    """Explorable view of every data source the agent can reach.

    Backs the clickable cards on the landing page. The optional ?view= query
    param (portfolio | market | policy | intelligence) selects the active panel.
    """
    clients = query_db("SELECT * FROM clients ORDER BY client_id")
    holdings = query_db(
        "SELECT client_id, ticker, company_name, shares, avg_cost_basis, "
        "current_price, sector, purchase_date FROM holdings "
        "ORDER BY client_id, ticker"
    )
    market = query_db("SELECT * FROM market_data ORDER BY sector, ticker")

    return templates.TemplateResponse(
        request,
        "data.html",
        {
            "app_name": CONFIG['app']['name'],
            "clients": clients,
            "holdings": holdings,
            "market": market,
            "policy_docs": list_policy_documents(),
            "tavily_cfg": CONFIG['tools']['tavily_search'],
            "tools_info": get_tools_info(),
        }
    )


# ==============================================================================
# System Integrity & Analytics Endpoints
# ==============================================================================

@app.get("/health")
async def health_check():
    """Mandatory deep health assessment verifying environment bindings and local dependencies."""
    status_report = {
        "status": "healthy",
        "checks": {
            "openai_api_key": "configured" if os.getenv("OPENAI_API_KEY") else "missing",
            "tavily_api_key": "configured" if os.getenv("TAVILY_API_KEY") else "missing",
            "sqlite_db_presence": "missing",
            "sqlite_db_connection": "failed",
            "vector_db_presence": "missing"
        }
    }
    
    # 1. Verify SQLite Database Presence and Connection Matrix
    db_path = CONFIG['paths']['sqlite_db']
    if os.path.exists(db_path):
        status_report["checks"]["sqlite_db_presence"] = "found"
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            cursor.close()
            conn.close()
            status_report["checks"]["sqlite_db_connection"] = "verified"
        except Exception as e:
            status_report["checks"]["sqlite_db_connection"] = f"failed: {str(e)}"
            status_report["status"] = "unhealthy"
    else:
        status_report["status"] = "unhealthy"

    # 2. Verify Persistent Vector Store Index Mapping
    vector_db_dir = CONFIG['paths']['vector_db_dir']
    db_name = CONFIG['rag']['retriever']['vector_db_name']
    faiss_file = os.path.join(vector_db_dir, f"{db_name}.faiss")
    if os.path.exists(faiss_file):
        status_report["checks"]["vector_db_presence"] = "found"
    else:
        status_report["checks"]["vector_db_presence"] = "missing (will build on first retrieval)"

    if status_report["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=status_report)
        
    return status_report


# ==============================================================================
# Functional Agent Execution Endpoints
# ==============================================================================
# NOTE: src/agents.py builds the agent with LangChain v1's `create_agent`, which
# compiles to a LangGraph graph. Its I/O contract is {"messages": [...]} in and
# {"messages": [...]} out — NOT the legacy {"input": ...}/{"output": ...} shape.


def _content_to_text(content):
    """Normalises message content (str or list-of-blocks) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", "") or block.get("content", "") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def run_agent_events(query: str):
    """Synchronous generator yielding structured execution events for the agent run.

    Event shapes (dicts):
      token        — a streamed delta of the final answer
      tool         — a tool invocation (id, name, args)            [concise trace]
      tool_result  — a tool's truncated result preview              [concise trace]
      log          — a verbose system line (full tool output, etc.) [exec trace]
      done / error — terminal markers
    """
    yield {"type": "log", "level": "system", "text": f"Query received: {query}"}
    yield {"type": "log", "level": "system", "text": "Streaming agent (LangGraph) with stream_mode=[updates, messages]"}

    seen_calls = set()
    try:
        for mode, chunk in agent.stream(
            {"messages": [{"role": "user", "content": query}]},
            stream_mode=["updates", "messages"],
        ):
            if mode == "messages":
                msg = chunk[0] if isinstance(chunk, (tuple, list)) else chunk
                if msg.__class__.__name__ == "AIMessageChunk":
                    text = _content_to_text(getattr(msg, "content", ""))
                    if text:
                        yield {"type": "token", "text": text}

            elif mode == "updates":
                for node, update in (chunk or {}).items():
                    if not isinstance(update, dict):
                        continue
                    yield {"type": "log", "level": "node", "text": f"Node '{node}' produced an update"}
                    for m in update.get("messages", []) or []:
                        cls = m.__class__.__name__
                        tool_calls = getattr(m, "tool_calls", None)

                        if tool_calls:
                            for tc in tool_calls:
                                tid = tc.get("id")
                                if tid in seen_calls:
                                    continue
                                seen_calls.add(tid)
                                name = tc.get("name")
                                tc_args = tc.get("args", {})
                                yield {"type": "tool", "id": tid, "name": name, "args": tc_args}
                                yield {"type": "log", "level": "tool_call",
                                       "text": f"TOOL CALL  {name}({json.dumps(tc_args, ensure_ascii=False)})"}

                        if cls == "ToolMessage":
                            full = "" if m.content is None else str(m.content)
                            preview = full if len(full) <= 280 else full[:280] + " …"
                            yield {"type": "tool_result", "id": getattr(m, "tool_call_id", None),
                                   "name": getattr(m, "name", None), "preview": preview}
                            yield {"type": "log", "level": "tool_result",
                                   "text": f"TOOL RESULT  {getattr(m, 'name', None)} →\n{full}"}

                        if cls == "AIMessage" and not tool_calls and getattr(m, "content", None):
                            yield {"type": "log", "level": "final", "text": "Final answer composed."}

        yield {"type": "log", "level": "system", "text": "Run complete."}
        yield {"type": "done"}
    except Exception as e:
        yield {"type": "log", "level": "error", "text": f"ERROR  {e}"}
        yield {"type": "error", "detail": str(e)}


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """Streams the agent run over a WebSocket: tokens, tool trace, and verbose logs.

    The blocking LangGraph generator runs on a worker thread; events are marshalled
    back to the event loop through an asyncio.Queue so the socket stays responsive.
    """
    await websocket.accept()
    try:
        payload = await websocket.receive_json()
        query = (payload.get("query") or "").strip()
        if not query:
            await websocket.send_json({"type": "error", "detail": "Empty query."})
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def produce():
            try:
                for event in run_agent_events(query):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as e:  # safety net; run_agent_events already guards
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "detail": str(e)})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # completion sentinel

        threading.Thread(target=produce, daemon=True).start()

        while True:
            event = await queue.get()
            if event is None:
                break
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.post("/api/chat", response_model=ChatResponse)
async def execution_query(payload: ChatRequest):
    """Non-streaming JSON endpoint (kept for health checks / programmatic use)."""
    try:
        result = agent.invoke({"messages": [{"role": "user", "content": payload.query}]})
        messages = result.get("messages", [])

        final_text = ""
        for m in reversed(messages):
            if m.__class__.__name__ == "AIMessage" and getattr(m, "content", None):
                final_text = _content_to_text(m.content)
                break

        tools_used = [
            getattr(m, "name", "tool")
            for m in messages
            if m.__class__.__name__ == "ToolMessage"
        ]

        return ChatResponse(
            response=final_text or "No response generated by the financial analyst agent.",
            tools_used=tools_used,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent Execution Failure: {str(e)}")