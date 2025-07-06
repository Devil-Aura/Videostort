"""
bot.py – Video-Sort Bot
• Forward videos (caption must contain episode number + 480p/720p/1080p).
• /setnames  – paste all episode titles (one per line)
• /setstickers – EITHER:
      a) reply to a sticker (run twice to save 2 stickers), OR
      b) /setstickers <id1> <id2>
• /publish – posts everything in order
"""

import re
from collections import defaultdict
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import Message

import config  # API_ID, API_HASH, BOT_TOKEN

# ── Pyrogram client ───────────────────────────────────────────────
app = Client(
    "video_sort_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

# ── Data store (RAM) ──────────────────────────────────────────────
class UserStore:
    def __init__(self):
        self.names: List[str] = []
        self.stickers: List[str] = []
        self.videos: Dict[int, Dict[str, str]] = defaultdict(dict)


users: Dict[int, UserStore] = defaultdict(UserStore)

QUALITY_TAGS = ["480p", "720p", "1080p"]
EP_RE = re.compile(r"episode\s*(\d{1,2})|\b(\d{1,2})\b", re.I)


def parse_video(msg: Message):
    """Return (episode:int | None, quality:str | None)."""
    text = (msg.caption or msg.video.file_name or "").lower()
    q = next((qt for qt in QUALITY_TAGS if qt in text), None)
    m = EP_RE.search(text)
    ep = int(m.group(1) or m.group(2)) if m else None
    return ep, q


# ── Commands ──────────────────────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    await m.reply(
        "👋 *Video-Sort Bot*\n\n"
        "1️⃣ Forward season videos (captions must contain episode number + quality).\n"
        "2️⃣ `/setnames` – paste titles.\n"
        "3️⃣ Reply to *two* stickers with `/setstickers`.\n"
        "4️⃣ `/publish` – bot posts everything. Enjoy! 🎉",
        quote=True,
    )


@app.on_message(filters.command("setnames") & filters.private)
async def cmd_setnames(_, m: Message):
    if len(m.text.split("\n")) < 2:
        return await m.reply(
            "❌ Send the episode list after the command:\n"
            "`/setnames`\n"
            "`Episode 01 - Pilot`\n"
            "`Episode 02 - …`",
            parse_mode="markdown",
            quote=True,
        )
    users[m.from_user.id].names = [ln.strip() for ln in m.text.split("\n")[1:] if ln.strip()]
    await m.reply(f"✅ Stored *{len(users[m.from_user.id].names)}* episode names.")


@app.on_message(filters.command(["setstickers", "addstickers"]) & filters.private)
async def cmd_setstickers(_, m: Message):
    store = users[m.from_user.id]

    # ── A. Reply-to-sticker mode ────────────────────────────────
    if m.reply_to_message and m.reply_to_message.sticker:
        fid = m.reply_to_message.sticker.file_id
        if fid in store.stickers:
            return await m.reply("⚠️ This sticker is already saved.", quote=True)
        if len(store.stickers) >= 2:
            store.stickers = []  # reset if user starts over
        store.stickers.append(fid)
        if len(store.stickers) == 1:
            await m.reply("✅ Sticker 1 saved. Now reply to the second sticker and send /setstickers.",
                          quote=True)
        else:
            await m.reply("✅ Sticker 2 saved. Both stickers are set!", quote=True)
        return

    # ── B. ID-parameters mode ──────────────────────────────────
    parts = m.text.strip().split(maxsplit=2)
    if len(parts) == 3:
        store.stickers = parts[1:]
        return await m.reply("✅ Two stickers saved via parameters!", quote=True)

    # ── Error message ──────────────────────────────────────────
    await m.reply(
        "❌ *How to use /setstickers*\n"
        "• *Preferred*: reply to a sticker and send /setstickers (do this twice).\n"
        "• Or: `/setstickers <file_id1> <file_id2>`",
        parse_mode="markdown",
        quote=True,
    )


@app.on_message(filters.video & filters.private & filters.forwarded)
async def on_forwarded_video(_, m: Message):
    ep, q = parse_video(m)
    if not ep or not q:
        return await m.reply(
            "❌ Caption or filename must include episode number *and* quality (480p/720p/1080p).",
            parse_mode="markdown",
            quote=True,
        )
    users[m.from_user.id].videos[ep][q] = m.video.file_id
    await m.reply(f"📥 Saved *Episode {ep:02d}* • *{q}*",
                  parse_mode="markdown")


@app.on_message(filters.command("publish") & filters.private)
async def cmd_publish(_, m: Message):
    s = users[m.from_user.id]
    if not s.names:
        return await m.reply("❌ Use /setnames first.")
    if len(s.stickers) < 2:
        return await m.reply("❌ You need two stickers — reply to them with /setstickers.")
    if not s.videos:
        return await m.reply("❌ No videos collected yet.")

    posted = 0
    for idx, title in enumerate(s.names, start=1):
        await app.send_message(m.chat.id, f"**{title}**", parse_mode="markdown")

        for q in QUALITY_TAGS:
            if q in s.videos.get(idx, {}):
                await app.send_video(m.chat.id, s.videos[idx][q], caption=q)

        await app.send_sticker(m.chat.id, s.stickers[0])
        await app.send_sticker(m.chat.id, s.stickers[1])
        posted += 1

    await m.reply(f"🎉 Posted *{posted}* episodes successfully!",
                  parse_mode="markdown")
