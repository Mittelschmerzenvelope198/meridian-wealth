# Meridian Wealth Partners: Financial Analyst Agentic Web App

This project transforms a local Jupyter Notebook-based ReAct agent into a production-ready, interactive web application. The application serves as an autonomous Financial Analyst Agent for Meridian Wealth Partners, capable of executing complex wealth management queries by orchestrating multiple data sources and tools.

## Project Overview

The Meridian Financial Analyst Agent is built using the LangChain v1 `create_agent` harness and powered by FastAPI. It is designed to assist relationship managers by:
1.  **Analyzing Portfolios:** Querying a SQLite database for client holdings, risk profiles, and allocations.
2.  **Tracking Market Data:** Retrieving stock prices, YTD returns, and analyst ratings from structured databases.
3.  **Calculating Metrics:** Performing real-time financial calculations (returns, percentages, comparisons).
4.  **Ensuring Policy Compliance:** Using a Retrieval-Augmented Generation (RAG) pipeline backed by FAISS to search across firm investment policy PDFs.
5.  **Gathering Market Intelligence:** Utilizing the Tavily Search API to pull live market news and RBI updates.

## Repository Structure

```text
meridian_analyst_agent/
├── data/
│   ├── policy_documents/    # PDF policy documents (Firm Guidelines)
│   └── meridian_wealth.db   # SQLite database (Clients, Holdings, Market Data)
├── vectordb/                # Persistent FAISS vector store storage
├── frontend/
│   ├── static/              # CSS and JavaScript assets
│   └── templates/           # HTML Jinja2 templates (index, chat, agent_info)
├── src/
│   ├── __init__.py
│   ├── config.py            # Centralized YAML configuration loader
│   ├── database_queries.py  # SQLite connection and query functions
│   ├── rag_pipeline.py      # PDF loading, embedding, and FAISS retrieval
│   ├── agents.py            # Tool definitions and ReAct agent initialization
│   └── schemas.py           # Pydantic schemas for API and Tool validation
├── app.py                   # FastAPI entry point and routing logic
├── config.yaml              # Centralized system configurations
├── .env                     # Environment variables (API Keys)
├── .gitignore               # Git ignore rules
├── README.md                # Project setup and overview
└── ARCHITECTURE.md          # Detailed system architecture documentation

```

## Setup Instructions (Windows)

Follow these instructions to set up the environment and run the application on a Windows machine.

### 1. Python 3.12 Installation

Ensure you have Python 3.12 installed using the Windows Package Manager (`winget`).

1. Open PowerShell and run the following command to download and install the latest Python 3.12.x version:
```powershell
winget install -e --id Python.Python.3.12

```


2. Close and reopen your PowerShell terminal to refresh your environment variables.
3. Verify your installation and check your default Python version:
```powershell
python --version

```


4. Confirm Python 3.12 is recognized in your Windows Python Launcher list:
```powershell
py --list

```


*Your output should look similar to this:*
```text
PS C:\Users\YourUser\Meridian Project Deployment> py --list
 -V:3.14 * Python 3.14 (64-bit)
 -V:3.13          Python 3.13 (Store)
 -V:3.12          Python 3.12 (64-bit)
 -V:3.11          Python 3.11 (64-bit)

```



### 2. Project Initialization

1. Open PowerShell.
2. Navigate to your desired workspace and create a new directory for the project:
```powershell
mkdir meridian_analyst_agent
cd meridian_analyst_agent

```


3. Use the provided `scaffold.py` script to generate the folder structure and initial files, then place your `meridian_wealth.db` and the 5 policy PDFs into the `data/` and `data/policy_documents/` folders, respectively.

### 3. Virtual Environment Setup

It is highly recommended to use a virtual environment to manage project dependencies. Since you may have multiple Python versions installed, explicitly target Python 3.12 for this environment.

1. Create a `.venv` virtual environment specifically using Python 3.12:
```powershell
py -3.12 -m venv .venv

```


2. Activate the virtual environment:
```powershell
.\.venv\Scripts\activate

```


*(You should see `(.venv)` appear at the beginning of your command prompt line).*

### 4. Install Dependencies

1. Create a `requirements.txt` file in the project root with the following content:
```text
fastapi
uvicorn
jinja2
pydantic
pyyaml
python-dotenv
sqlite3
langchain
langchain-core
langchain-openai
langchain-community
langchain-tavily
langgraph
faiss-cpu
pypdf
tavily-python

```


2. Install the required packages using `pip`:
```powershell
pip install -r requirements.txt

```



### 5. Environment Variables Configuration

1. Open the `.env` file located in the root directory.
2. Add your OpenAI and Tavily API keys:
```env
OPENAI_API_KEY=sk-your_actual_openai_api_key_here
TAVILY_API_KEY=tvly-your_actual_tavily_api_key_here

```


*Note: Do not commit the `.env` file to version control.*

### 6. Verify System Health and Build Vector Database

Before launching the full application, it's good practice to verify the setup.

1. Start the FastAPI server:
```powershell
uvicorn app:app --reload

```


2. Open your web browser and navigate to the health check endpoint:
`http://127.0.0.1:8000/health`
* This endpoint verifies API keys, SQLite database connectivity, and the FAISS index.
* **Important:** On the very first run (or first API request), the application will automatically read the PDFs in `data/policy_documents/`, embed them using OpenAI, and save the persistent FAISS index to the `vectordb/` folder. This may take a few moments. Subsequent startups will load the index from the disk almost instantly.



### 7. Run the Application

1. If the server is not already running, start it:
```powershell
uvicorn app:app --reload

```


*The `--reload` flag enables auto-reloading upon code changes.*
2. Access the application interfaces:
* **Landing Page:** `http://127.0.0.1:8000/`
* **Chat Interface:** `http://127.0.0.1:8000/chat`
* **Agent Configuration Info:** `http://127.0.0.1:8000/agent_info`



## Usage Example

Navigate to the Chat interface (`/chat`) and test the agent with a complex query, such as:

> *"Compare the IT sector exposure of Client CLT-001 and Client CLT-002. Which client is more overweight in IT? Check our sector concentration policy limits from the policy documents and recommend if either client needs to trim IT positions. Also look up the latest market outlook for Indian IT sector."*

Watch the agent autonomously select the appropriate SQL, RAG, and Web Search tools to synthesize a complete answer.

## Application Interfaces

Once the server is running, the app exposes the following pages and endpoints:

| Route          | Description                                                                 |
| -------------- | --------------------------------------------------------------------------- |
| `/`            | Landing page with clickable cards into each data source                     |
| `/chat`        | Streaming chat workspace with a live tool-trace panel and verbose execution trace (over WebSocket) |
| `/data`        | Data Explorer — browse the SQLite clients/holdings/market tables and policy documents |
| `/agent_info`  | Detailed catalogue of the agent's tools and the loaded configuration        |
| `/health`      | JSON health check (database, vector store, API key presence)                |
| `/api/chat`    | Non-streaming JSON chat endpoint                                             |
| `/ws/chat`     | WebSocket endpoint powering the streaming chat                              |

## Production Deployment (AWS EC2)

To deploy this application to a public server (Ubuntu on AWS EC2, behind Nginx, managed
by `systemd`), follow the complete step-by-step guide:

➡️ **[EC2_Deployment.md](EC2_Deployment.md)**

It covers launching the instance (`t3.medium`, Ubuntu 24.04 LTS, 20 GB gp3), installing
Python 3.12 and system packages, configuring the firewall, creating the `systemd`
service, setting up the Nginx reverse proxy (including the **WebSocket** configuration
required by the chat), viewing logs, optional HTTPS via Certbot, and troubleshooting.
