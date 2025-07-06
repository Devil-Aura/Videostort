"""
config.py
~~~~~~~~~
Central place for secrets and basic constants.
Load values from environment variables so you never hard-code them.
"""

import os

API_ID: int = int(os.getenv("API_ID", 123456))              # ← put real int
API_HASH: str = os.getenv("API_HASH", "YOUR_API_HASH")      # ← put real hash
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")   # ← bot token

# If you want owner-only commands later:
OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "").split()}  # e.g. "123 456"
