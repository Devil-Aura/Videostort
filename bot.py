"""
bot.py
~~~~~~
All Pyrogram handlers live here.
"""

import re
from collections import defaultdict
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

import config  # your credentials

# ── 1.  Pyrogram Client ──────────────────────────────────────────────
app = Client(
    "video_sort_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

# ── 2.  In-memory storage (per-user) ─────────────────────────────────
class UserStore:
    def __init__(self) -> None:
        self.names: List[str] = []                # list of episode title lines
        self.stickers: List[str] = []             # [sticker_id_1, sticker_id_2]
        self.videos: Dict[int, Dict[str, str]] = defaultdict(dict)  # ep → quality → file_id


users: Dict[int, UserStore] = defaultdict(UserStore)

# ── 3.  Constants & helpers ─────────────────────────────────────────
QUALITY_TAGS = ["480p", "720p", "1080p"]
EP_RE = re.compile(r"episode\\s*(\\d{1,2})|\\b(\\d{1,2})\\b", re.I)


def parse_video(msg: Message):
    """Return (episode:int, quality:str) or (None, None) if not found."""
    text = (msg.caption or msg.video.file_name or "").lower()
    quality = next((q for q in QUALITY_TAGS if q in text), None)
    m = EP_RE.search(text)
    ep = int(m.group(1) or m.group(2)) if m else None
    return ep, quality


# ── 4.  Command handlers ────────────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    await m.reply(
        "👋 *Video-Sort Bot*\n"
        "Forward your season videos to me, then use /setnames, /setstickers and /publish.",
        quote=True,
    )


@app.on_message(filters.command("setnames") & filters.private)
async def cmd_setnames(_, m: Message):
    # everything after the first newline are episode lines
    if len(m.text.split("\n")) < 2:
        return await m.reply(
            "Send the episode list after the command, e.g.\n"
            "`/setnames Episode 01 - Pilot`\\n`Episode 02 - ...`",
            quote=True,
        )
    names = [ln.strip() for ln in m.text.split("\n")[1:] if ln.strip()]
    users[m.from_user.id].names = names
    await m.reply(f"✅ Stored *{len(names)}* episode names.")


@app.on_message(filters.command("setstickers") & filters.private)
async def cmd_setstickers(_, m: Message):
    parts = m.text.strip().split()
    if len(parts) != 3:
        return await m.reply(
            "Usage: `/setstickers <sticker_file_id1> <sticker_file_id2>`",
            quote=True,
        )
    users[m.from_user.id].stickers = parts[1:]
    await m.reply("✅ Stickers saved.")


@app.on_message(filters.video & filters.private & filters.forwarded)
async def on_forwarded_video(_, m: Message):
    ep, quality = parse_video(m)
    if not ep or not quality:
        return await m.reply(
            "❗️Caption or filename must contain the episode number "
            "*and* a quality tag (480p / 720p / 1080p).",
            quote=True,
        )
    store = users[m.from_user.id]
    store.videos[ep][quality] = m.video.file_id
    await m.reply(
        f"📥 Saved *Episode {ep:02d}* • *{quality}* "
        f"(episodes collected: {len(store.videos)})"
    )


@app.on_message(filters.command("publish") & filters.private)
async def cmd_publish(_, m: Message):
    store = users[m.from_user.id]

    if not store.names:
        return await m.reply("Set episode names first using /setnames.")
    if len(store.stickers) < 2:
        return await m.reply("Set two stickers first with /setstickers.")
    if not store.videos:
        return await m.reply("No videos collected yet.")

    chat_id = m.chat.id

    for idx, name_line in enumerate(store.names, start=1):
        await app.send_message(chat_id, f"**{name_line}**", parse_mode="markdown")

        for qual in QUALITY_TAGS:
            if qual in store.videos.get(idx, {}):
                await app.send_video(chat_id, store.videos[idx][qual], caption=qual)

        await app.send_sticker(chat_id, store.stickers[0])
        await app.send_sticker(chat_id, store.stickers[1])

    await m.reply("🎉 All episodes published! Use /start to begin a new season.")
