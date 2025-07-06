"""
bot.py – All bot logic and command handlers
"""

import re
from collections import defaultdict
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import Message

import config  # credentials from config.py

# ── 1. Start the bot ────────────────────────────────
app = Client(
    "video_sort_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

# ── 2. In-memory storage ────────────────────────────
class UserStore:
    def __init__(self):
        self.names: List[str] = []                # Episode titles
        self.stickers: List[str] = []             # Two sticker file_ids
        self.videos: Dict[int, Dict[str, str]] = defaultdict(dict)  # ep → quality → file_id

users: Dict[int, UserStore] = defaultdict(UserStore)

QUALITY_TAGS = ["480p", "720p", "1080p"]
EP_RE = re.compile(r"episode\s*(\d{1,2})|\b(\d{1,2})\b", re.I)


# ── 3. Helper to extract ep & quality ───────────────
def parse_video(msg: Message):
    text = (msg.caption or msg.video.file_name or "").lower()
    quality = next((q for q in QUALITY_TAGS if q in text), None)
    m = EP_RE.search(text)
    ep = int(m.group(1) or m.group(2)) if m else None
    return ep, quality


# ── 4. Commands ─────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    await m.reply(
        "👋 *Welcome to Video-Sort Bot!*\n\n"
        "✅ Forward your episode videos (captions must include episode number and quality: 480p/720p/1080p)\n"
        "✅ Then send /setnames and paste all episode names\n"
        "✅ Then /setstickers with 2 sticker file_ids\n"
        "✅ Finally, /publish to auto-post everything 🎉",
        quote=True
    )


@app.on_message(filters.command("setnames") & filters.private)
async def cmd_setnames(_, m: Message):
    if len(m.text.split("\n")) < 2:
        return await m.reply(
            "❌ Please send the episode names after the command.\n\n"
            "✅ Example:\n"
            "`/setnames`\n"
            "`Episode 01 - Start`\n"
            "`Episode 02 - The Next One`",
            parse_mode="markdown",
            quote=True
        )
    users[m.from_user.id].names = [line.strip() for line in m.text.split("\n")[1:] if line.strip()]
    await m.reply(f"✅ Stored *{len(users[m.from_user.id].names)}* episode names.")


@app.on_message(filters.command(["setstickers", "addstickers"]) & filters.private)
async def cmd_setstickers(_, m: Message):
    parts = m.text.strip().split(maxsplit=2)
    if len(parts) != 3:
        return await m.reply(
            "❌ Correct Usage:\n`/setstickers <sticker_file_id1> <sticker_file_id2>`",
            parse_mode="markdown",
            quote=True
        )
    users[m.from_user.id].stickers = parts[1:]
    await m.reply("✅ Stickers saved successfully!")


@app.on_message(filters.video & filters.private & filters.forwarded)
async def on_forwarded_video(_, m: Message):
    ep, quality = parse_video(m)
    if not ep or not quality:
        return await m.reply(
            "❌ Couldn't detect episode number or quality!\n"
            "Make sure caption or filename includes both.",
            quote=True
        )

    users[m.from_user.id].videos[ep][quality] = m.video.file_id
    await m.reply(f"📥 Saved: *Episode {ep:02d}* • *{quality}*", parse_mode="markdown")


@app.on_message(filters.command("publish") & filters.private)
async def cmd_publish(_, m: Message):
    store = users[m.from_user.id]
    
    if not store.names:
        return await m.reply("❌ Please set episode names first using /setnames.")
    if len(store.stickers) < 2:
        return await m.reply("❌ You must set 2 sticker file IDs using /setstickers.")
    if not store.videos:
        return await m.reply("❌ No videos have been saved yet.")

    chat_id = m.chat.id
    count = 0

    for idx, title in enumerate(store.names, start=1):
        await app.send_message(chat_id, f"**{title}**", parse_mode="markdown")

        for q in QUALITY_TAGS:
            if q in store.videos.get(idx, {}):
                await app.send_video(chat_id, store.videos[idx][q], caption=q)

        await app.send_sticker(chat_id, store.stickers[0])
        await app.send_sticker(chat_id, store.stickers[1])
        count += 1

    await m.reply(f"🎉 Successfully posted *{count}* episodes!", parse_mode="markdown")
