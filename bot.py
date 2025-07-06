"""
bot.py – Video-Sort Bot  (2025-07-06)

Flow
----
/sort [label]      – start a new session
/setnames          – paste episode titles
/setstickers       – reply to two stickers (run twice) or give 2 IDs
/publish           – bot posts: bold title, 3 quality videos, 2 stickers
"""

import asyncio
import re
from collections import defaultdict
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message

import config


# ── 1.  Pyrogram client ───────────────────────────────────────────
app = Client(
    "video_sort_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

# ── 2.  Per-user RAM store ────────────────────────────────────────
class UserStore:
    def __init__(self):
        self.names: List[str] = []
        self.stickers: List[str] = []
        self.videos: Dict[int, Dict[str, str]] = defaultdict(dict)
        self.label: str = ""


users: Dict[int, UserStore] = defaultdict(UserStore)

QUALITY_TAGS = ["480p", "720p", "1080p"]


# ── 3.  Helper: parse video caption/filename ──────────────────────
def parse_video(msg: Message):
    """Return (episode:int | None, quality:str | None)."""
    text = (msg.caption or msg.video.file_name or "").lower()

    # quality
    quality = next((q for q in QUALITY_TAGS if q in text), None)

    # episode number patterns: Episode 07, Ep07, E07, S01E07, etc.
    m = re.search(r"(?:episode|ep|e|s\d+e)(\d{1,2})", text, re.I)
    ep = int(m.group(1)) if m else None

    return ep, quality


def store(user_id: int) -> UserStore:
    return users[user_id]


# ── 4.  Helper: safe call with FloodWait handling ─────────────────
async def safe_call(func, *args, **kwargs):
    """Retry Telegram API call on FloodWait."""
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)  # wait & retry


# ── 5.  /start ────────────────────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    await m.reply(
        "👋 **Video-Sort Bot**\n"
        "`/sort` → `/setnames` → `/setstickers` → `/publish`",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
    )


# ── 6.  /sort ─────────────────────────────────────────────────────
@app.on_message(filters.command("sort") & filters.private)
async def cmd_sort(_, m: Message):
    label = " ".join(m.command[1:]).strip() or "New Session"
    s = store(m.from_user.id)
    s.names.clear()
    s.stickers.clear()
    s.videos.clear()
    s.label = label
    await m.reply(
        f"✅ Sorting session **{label}** started.\n"
        "Forward all videos now, then run `/setnames`, `/setstickers`, `/publish`.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── 7.  /setnames ────────────────────────────────────────────────
@app.on_message(filters.command("setnames") & filters.private)
async def cmd_setnames(_, m: Message):
    titles = [ln.strip() for ln in m.text.split("\n")[1:] if ln.strip()]
    if not titles:
        return await m.reply(
            "❌ Paste episode titles after the command.",
            quote=True,
        )
    store(m.from_user.id).names = titles
    await m.reply(f"✅ Stored **{len(titles)}** episode names.", parse_mode=ParseMode.MARKDOWN)


# ── 8.  /setstickers ─────────────────────────────────────────────
@app.on_message(filters.command(["setstickers", "addstickers"]) & filters.private)
async def cmd_setstickers(_, m: Message):
    s = store(m.from_user.id)

    # A. reply-to-sticker mode
    if m.reply_to_message and m.reply_to_message.sticker:
        fid = m.reply_to_message.sticker.file_id
        if fid in s.stickers:
            return await m.reply("⚠️ Already saved.", quote=True)
        if len(s.stickers) >= 2:
            s.stickers.clear()
        s.stickers.append(fid)
        msg = ("✅ Sticker 1 saved. Reply to second sticker and repeat."
               if len(s.stickers) == 1
               else "✅ Both stickers saved!")
        return await m.reply(msg, quote=True)

    # B. parameters mode
    parts = m.text.split()
    if len(parts) == 3:
        s.stickers = parts[1:]
        return await m.reply("✅ Stickers saved via parameters!", quote=True)

    # C. error
    await m.reply(
        "Usage:\n• Reply to a sticker and send `/setstickers` (twice), "
        "or `/setstickers <id1> <id2>`",
        quote=True,
    )


# ── 9.  Video intake ─────────────────────────────────────────────
@app.on_message(filters.video & filters.private)
async def on_video(_, m: Message):
    ep, q = parse_video(m)
    if not ep or not q:
        return await m.reply(
            "❌ Caption or filename must include episode number + 480p/720p/1080p.",
            quote=True,
        )
    store(m.from_user.id).videos[ep][q] = m.video.file_id
    await m.reply(f"📥 Saved **Episode {ep:02d} • {q}**", parse_mode=ParseMode.MARKDOWN)


# ── 10. /publish ────────────────────────────────────────────────
@app.on_message(filters.command("publish") & filters.private)
async def cmd_publish(_, m: Message):
    s = store(m.from_user.id)

    # basic checks
    if not s.names:
        return await m.reply("❌ Run /setnames first.", quote=True)
    if len(s.stickers) < 2:
        return await m.reply("❌ Need two stickers via /setstickers.", quote=True)
    if not s.videos:
        return await m.reply("❌ No videos collected.", quote=True)

    posted = 0
    for idx, title in enumerate(s.names, start=1):
        # bold episode title
        await safe_call(app.send_message, m.chat.id, f"**{title}**", parse_mode=ParseMode.MARKDOWN)

        # 3 qualities (NO caption, so original filename shows)
        for q in QUALITY_TAGS:
            if q in s.videos.get(idx, {}):
                await safe_call(app.send_video, m.chat.id, s.videos[idx][q])
                await asyncio.sleep(1)  # small delay between videos

        # two stickers
        await safe_call(app.send_sticker, m.chat.id, s.stickers[0])
        await safe_call(app.send_sticker, m.chat.id, s.stickers[1])

        posted += 1
        await asyncio.sleep(1.5)  # delay between episodes

    await m.reply(f"🎉 Posted **{posted}** episodes successfully!", parse_mode=ParseMode.MARKDOWN)
