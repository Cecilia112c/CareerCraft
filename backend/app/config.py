import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]          # CareerCraft/
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "backend" / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
for _d in (DATA_DIR, UPLOAD_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_DAYS = 7
PUSH_TICK_MINUTES = int(os.getenv("PUSH_TICK_MINUTES", "15"))
TIMEZONE = "Asia/Shanghai"
MAX_UPLOAD_MB = 10
