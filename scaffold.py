import os
from pathlib import Path

def create_project_scaffold():
    """Generates the folders and files for the Financial Analyst Agentic Web App."""
    
    # 1. Define the folder structure
    folders = [
        "data/policy_documents",
        "vectordb",
        "frontend/templates",
        "frontend/static",
        "src"
    ]

    # 2. Define the files and their initial boilerplate/comments
    files = {
        # Frontend
        "frontend/templates/index.html": "\n",
        "frontend/static/style.css": "/* Application styling */\n",
        "frontend/static/app.js": "// Asynchronous API calls and DOM manipulation\n",
        
        # Backend Source Code
        "src/agents.py": "# ReAct agent definition and tool wrappers\n",
        "src/database_queries.py": "# SQLite connection handling and data retrieval functions\n",
        "src/rag_pipeline.py": "# Document loading, embedding, and FAISS vector store management\n",
        "src/schemas.py": "# Pydantic models for data validation and API typing\n",
        
        # Project Root
        "app.py": "# FastAPI application entry point and routing\n",
        ".env": "OPENAI_API_KEY=your_openai_key_here\nTAVILY_API_KEY=your_tavily_key_here\n",
        ".gitignore": ".env\n__pycache__/\n*.pyc\n.venv/\nvenv/\n",
        "README.md": "# Meridian Wealth Partners - Financial Analyst Agent\n\nInstructions for setup and execution will go here.\n",
        "ARCHITECTURE.md": "# Architecture Overview\n\nDocumentation of the ReAct flow, RAG pipeline, and tool orchestration.\n"
    }

    print("🚀 Scaffolding Meridian Wealth Partners Project...")

    # Create directories
    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)
        print(f"📁 Created folder: {folder}")

    # Create files
    for filepath, content in files.items():
        file_path = Path(filepath)
        # Only write if the file doesn't already exist to prevent accidental overwrites
        if not file_path.exists():
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"📄 Created file:   {filepath}")
        else:
            print(f"⚠️ Skipped (already exists): {filepath}")

    print("\n✅ Scaffolding complete! You can now move your meridian_wealth.db and policy PDFs into the /data folder.")

if __name__ == "__main__":
    create_project_scaffold()