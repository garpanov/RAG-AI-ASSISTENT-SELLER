"""Make this nested standalone project's package importable during collection."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

os.environ.setdefault("ORDERS_API_KEY", "orders-secret")
os.environ.setdefault("WEBHOOK_SECRET", "hook-secret")

