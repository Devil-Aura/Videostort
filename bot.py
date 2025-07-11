import asyncio
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message

import config

app = Client(
    "video_sort_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

QUALITY_TAGS = ["360p", "480p", "720p", "1080p"]
QUALITY_ALIAS = {
    "360p": "480p",
    "480p": "480p",
    "720p": "720p",
    "1080p": "1080p"
}


class UserStore:
    def __init__(self):
        self.names: List[str] = []
        self.caption_format: str = ""
        self.stickers: List[str] = []
        self.videos: Dict[int, Dict[str, Tuple[str, str]]] = defaultdict(dict)
        self.label: str = ""


users: Dict[int, UserStore] = defaultdict(UserStore)


def parse_video(msg: Message):
    text = (msg.caption or msg.video.file_name or "").lower()
    original = msg.caption or msg.video.file_name or "Video"

    quality_raw = next((q for q in QUALITY_TAGS if q in text), None)
    quality = QUALITY_ALIAS.get(quality_raw)

    m = re.search(r"(?:episode|ep|e|s\d+e)(\d{1,2})", text, re.I)
    episode = int(m.group(1)) if m else None

    return episode, quality, original


async def safe_call(func, *args, **kwargs):
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)


@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, m: Message):
    await m.reply(
        "👋 **Video-Sort Bot**\n"
        "`/sort` ➜ `/setnames` ➜ `/setformat` ➜ `/setstickers` ➜ `/publish`",
        parse_mode=ParseMode.MARKDOWN,
        quote=True,
    )


@app.on_message(filters.command("sort") & filters.private)
async def cmd_sort(_, m: Message):
    label = " ".join(m.command[1:]).strip() or "New Session"
    s = users[m.from_user.id]
    s.names.clear()
    s.caption_format = ""
    s.stickers.clear()
    s.videos.clear()
    s.label = label
    await m.reply(
        f"✅ Sorting session **{label}** started.\n"
        "Forward videos, then do `/setnames`, `/setformat`, `/setstickers`, `/publish`.",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("setnames") & filters.private)
async def cmd_setnames(_, m: Message):
    titles = [ln.strip() for ln in m.text.split("\n")[1:] if ln.strip()]
    if not titles:
        return await m.reply("❌ Paste episode titles after the command.", quote=True)
    users[m.from_user.id].names = titles
    await m.reply(f"✅ Stored **{len(titles)}** episode names.", parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("setformat") & filters.private)
async def cmd_setformat(_, m: Message):
    lines = m.text.splitlines()
    fmt = "\n".join(line for line in lines if not line.strip().startswith("/setformat")).strip()

    if not fmt:
        return await m.reply("❌ Please provide a caption format after the command.", quote=True)

    users[m.from_user.id].caption_format = fmt
    await m.reply(
        "✅ Caption format saved!\nUse `{ep}` for episode number and `{quality}` for quality.",
        parse_mode=None,
        quote=True,
    )


@app.on_message(filters.command(["setstickers", "addstickers"]) & filters.private)
async def cmd_setstickers(_, m: Message):
    s = users[m.from_user.id]

    # Reply-to-sticker mode
    if m.reply_to_message and m.reply_to_message.sticker:
        fid = m.reply_to_message.sticker.file_id
        if fid in s.stickers:
            return await m.reply("⚠️ Already saved.", quote=True)
        if len(s.stickers) >= 2:
            s.stickers.clear()
        s.stickers.append(fid)
        text = ("✅ Sticker 1 saved. Reply to second sticker and repeat."
                if len(s.stickers) == 1 else "✅ Sticker 2 saved – done!")
        return await m.reply(text, quote=True)

    # Parameter mode
    parts = m.text.split()
    if len(parts) == 3:
        s.stickers = parts[1:]
        return await m.reply("✅ Stickers saved via parameters!", quote=True)

    await m.reply(
        "Reply to a sticker with `/setstickers` (do this twice) **or** `/setstickers id1 id2`.",
        quote=True,
    )


@app.on_message(filters.video & filters.private)
async def on_video(_, m: Message):
    ep, q, original = parse_video(m)
    if not ep or not q:
        return await m.reply(
            "❌ Caption or filename must include episode number and 480p / 720p / 1080p / 360p.",
            quote=True,
        )
    users[m.from_user.id].videos[ep][q] = (m.video.file_id, original)
    await m.reply(
        f"📥 Saved **Episode {ep:02d} • {q}**",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("publish") & filters.private)
async def cmd_publish(_, m: Message):
    s = users[m.from_user.id]

    if not s.names:
        return await m.reply("❌ Run /setnames first.", quote=True)
    if not s.caption_format:
        return await m.reply("❌ Please set caption template using /setformat.", quote=True)
    if len(s.stickers) < 2:
        return await m.reply("❌ Need two stickers via /setstickers.", quote=True)
    if not s.videos:
        return await m.reply("❌ No videos collected.", quote=True)

    posted = 0
    for idx, title in enumerate(s.names, start=1):
        await safe_call(app.send_message, m.chat.id, f"**{title}**", parse_mode=ParseMode.MARKDOWN)

        for q in ["480p", "720p", "1080p"]:
            if q in s.videos.get(idx, {}):
                fid, original_name = s.videos[idx][q]
                raw = s.caption_format.format(ep=f"{idx:02d}", quality=q)
                caption = "\n".join(f"**{line}**" for line in raw.splitlines())

                await safe_call(
                    app.send_video,
                    m.chat.id,
                    fid,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    file_name=original_name
                )
                await asyncio.sleep(1)

        await safe_call(app.send_sticker, m.chat.id, s.stickers[0])
        await safe_call(app.send_sticker, m.chat.id, s.stickers[1])
        posted += 1
        await asyncio.sleep(1.5)

    await m.reply(f"🎉 Posted **{posted}** episodes successfully!", parse_mode=ParseMode.MARKDOWN)
