from pathlib import Path

APP_NAME = "Texx"
DEFAULT_ASSISTANT_NAME = "Texx"
DATA_DIR = Path.home() / ".local" / "share" / "texx"
DB_PATH = DATA_DIR / "texx.db"
CONFIDENCE_EXECUTE_THRESHOLD = 0.85
CONFIDENCE_LLM_FALLBACK = 0.75
