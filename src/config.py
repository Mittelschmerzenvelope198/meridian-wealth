import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def load_config():
    """Loads the config.yaml parameters from the workspace root."""
    base_dir = Path(__file__).resolve().parent.parent
    config_path = base_dir / "config.yaml"
    
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    
    config['paths']['sqlite_db'] = str(base_dir / config['paths']['sqlite_db'])
    config['paths']['policy_documents_dir'] = str(base_dir / config['paths']['policy_documents_dir'])
    config['paths']['vector_db_dir'] = str(base_dir / config['paths']['vector_db_dir'])
    
    return config

CONFIG = load_config()

if not os.getenv("OPENAI_API_KEY") or not os.getenv("TAVILY_API_KEY"):
    raise ValueError("Missing critical configuration keys in workspace .env configuration.")