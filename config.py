"""
config.py
~~~~~~~~~
Centralised configuration.
Fill the environment variables or replace the fall-backs below.
"""

import os

API_ID: int   = int(os.getenv("API_ID", 22768311))            # ← your int
API_HASH: str = os.getenv("API_HASH", "702d8884f48b42e865425391432b3794")      # ← your hash
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")   # ← your token

# Optional: restrict commands to specific owners
OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "6040503076").split()}
