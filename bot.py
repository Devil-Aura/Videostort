"""
bot.py – Video-Sort Bot

Commands
--------
/start          – basic help
/sort [label]   – begin new sorting session (clears previous data)
/setnames       – paste episode titles (one per line)
/setstickers    – reply to 2 stickers (run twice) or pass 2 IDs
/publish        – post sorted episodes (title + 3 qualities + 2 stickers)
"""

import re
from collections import defaultdict
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

import config


# ── 1.  Pyrogram client ──────────────────────────────────────────
app = Client(
    "video_sort_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)


# ── 2.  Per-user RAM store ───────────────────────────────────────
class UserStore:
    def __init__(self) -> None:
        self.names: List[str] = []
        self.stickers: List[str] = []
        self.videos: Dict[int, Dict[str, str]] = defaultdict(dict)
        self.label: str = ""          # optional session name


users: Dict[int, UserStore] = defaultdict(UserStore)


# ── 3.  Helpers ─────────────────────────────────────────────────
QUALITY_TAGS = ["480p", "720p", "1080p"]
EP_RE = re.compile(r"episode\s*(\d{1,2})|\b(\d{1,2})\b", re.I)


def parse_video(msg: Message):
    """
    Extract (episode:int, quality:str) from caption or file name.
    Returns (None, None) if not found.
    """
    text = (msg.caption or msg.video.file_name or "").lower()
    quality = next((q for q in QUALITY_TAGS if q in text), None)
    m = EP_RE.search(text)
    ep = int(m.group(1) or m.group(2)) if m else None
    return ep, quality


def get_store(user_id: int) -> UserStore:
    return users[user_id]


# ── 4.  Command: /start ─────────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    await m.reply(
        "👋 **Video-Sort Bot**\n\n"
        "• `/sort` – start a new season upload\n"
        "• `/setnames` – paste all episode titles\n"
        "• `/setstickers` – reply to two stickers (run twice)\n"
        "• `/publish` – get the sorted post\n\n"
        "Captions or filenames **must** contain episode number and quality "
        "(480p/720p/1080p).",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
    )


# ── 5.  Command: /sort ──────────────────────────────────────────
@app.on_message(filters.command("sort") & filters.private)
async def cmd_sort(_, m: Message):
    label = " ".join(m.command[1:]).strip()
    store = get_store(m.from_user.id)
    store.names.clear()
    store.stickers.clear()
    store.videos.clear()
    store.label = label or "New Session"

    await m.reply(
        f"✅ Sorting session **{store.label}** started!\n"
        "Now send/forward all episode videos.\n"
        "After that, use `/setnames`, `/setstickers`, and finally `/publish`.",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
    )


# ── 6.  Command: /setnames ──────────────────────────────────────
@app.on_message(filters.command("setnames") & filters.private)
async def cmd_setnames(_, m: Message):
    lines = m.text.split("\n")[1:]  # skip the command line itself
    titles = [ln.strip() for ln in lines if ln.strip()]
    if not titles:
        return await m.reply(
            "❌ Send the episode list right after the command, e.g.\n"
            "`/setnames`\n`Episode 01 - Pilot`\n`Episode 02 - ...`",
            parse_mode=ParseMode.MARKDOWN,
            quote=True,
        )
    get_store(m.from_user.id).names = titles
    await m.reply(f"✅ Stored **{len(titles)}** episode names.",
                  parse_mode=ParseMode.MARKDOWN)


# ── 7.  Command: /setstickers ───────────────────────────────────
@app.on_message(filters.command(["setstickers", "addstickers"]) & filters.private)
async def cmd_setstickers(_, m: Message):
    store = get_store(m.from_user.id)

    # A. Reply-to-sticker mode
    if m.reply_to_message and m.reply_to_message.sticker:
        fid = m.reply_to_message.sticker.file_id
        if fid in store.stickers:
            return await m.reply("⚠️ This sticker is already saved.", quote=True)
        if len(store.stickers) >= 2:
            store.stickers.clear()   # reset if user starts over
        store.stickers.append(fid)
        msg = ("✅ Sticker 1 saved. Reply to the second sticker and send /setstickers."
               if len(store.stickers) == 1
               else "✅ Sticker 2 saved. Both stickers are set!")
        return await m.reply(msg, quote=True)

    # B. Two IDs in parameters
    parts = m.text.strip().split(maxsplit=2)
    if len(parts) == 3:
        store.stickers = parts[1:]
        return await m.reply("✅ Two stickers saved via parameters!", quote=True)

    # C. Wrong usage
    await m.reply(
        "❌ *Usage*\n"
        "• Reply to a sticker and send `/setstickers` (do this twice)\n"
        "• OR `/setstickers <id1> <id2>`",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
    )


# ── 8.  Video intake ────────────────────────────────────────────
@app.on_message(filters.video & filters.private)
async def on_video(_, m: Message):
    ep, q = parse_video(m)
    if not ep or not q:
        return await m.reply(
            "❌ Caption or filename must include episode number **and** quality "
            "(480p / 720p / 1080p).",
            parse_mode=ParseMode.MARKDOWN,
            quote=True,
        )
    store = get_store(m.from_user.id)
    store.videos[ep][q] = m.video.file_id
    await m.reply(f"📥 Saved **Episode {ep:02d}** • **{q}**",
                  parse_mode=ParseMode.MARKDOWN)


# ── 9.  Command: /publish ───────────────────────────────────────
@app.on_message(filters.command("publish") & filters.private)
async def cmd_publish(_, m: Message):
    s = get_store(m.from_user.id)

    if not s.names:
        return await m.reply("❌ Use /setnames first.", quote=True)
    if len(s.stickers) < 2:
        return await m.reply("❌ Set two stickers via /setstickers.", quote=True)
    if not s.videos:
        return await m.reply("❌ No videos collected yet.", quote=True)

    posted = 0
    for idx, title in enumerate(s.names, start=1):
        await app.send_message(m.chat.id, f"**{title}**", parse_mode=ParseMode.MARKDOWN)

        for q in QUALITY_TAGS:
            if q in s.videos.get(idx, {}):
                await app.send_video(m.chat.id, s.videos[idx][q], caption=q)

        await app.send_sticker(m.chat.id, s.stickers[0])
        await app.send_sticker(m.chat.id, s.stickers[1])
        posted += 1

    await m.reply(f"🎉 Posted **{posted}** episodes successfully!",
                  parse_mode=ParseMode.MARKDOWN)
