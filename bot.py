import asyncio
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import config

app = Client(
    "video_sort_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
)

# Support quality with or without "p"
QUALITY_TAGS = ["360", "360p", "480", "480p", "720", "720p", "1080", "1080p"]
QUALITY_ALIAS = {
    "360": "480p",
    "360p": "480p",
    "480": "480p",
    "480p": "480p",
    "720": "720p",
    "720p": "720p",
    "1080": "1080p",
    "1080p": "1080p",
}


class UserStore:
    def __init__(self):
        self.names: List[str] = []
        self.caption_format: str = ""
        self.stickers: List[str] = []
        self.videos: Dict[int, Dict[str, Tuple[str, str]]] = defaultdict(dict)
        self.label: str = ""
        self.ignore: str = ""  # store user-defined ignore string
        self.start_ep: int = 1  # default starting episode
        self.ep_mode: str = "normal"  # global toggle: normal or 001


# New class for quality sort feature
class QualitySortStore:
    def __init__(self):
        self.caption_format: str = ""
        self.videos: Dict[int, Dict[str, str]] = defaultdict(dict)  # {ep: {quality: file_id}}
        self.is_active: bool = False
        self.ep_mode: str = "normal"


users: Dict[int, UserStore] = defaultdict(UserStore)
quality_users: Dict[int, QualitySortStore] = {}


def parse_video(msg: Message):
    text = (msg.caption or msg.video.file_name or "").lower()
    original = msg.caption or msg.video.file_name or "Video"

    # Apply ignore filter
    s = users[msg.from_user.id]
    if s.ignore:
        text = text.replace(s.ignore.lower(), "")

    # Detect quality
    quality_raw = next((q for q in QUALITY_TAGS if q in text), None)
    quality = QUALITY_ALIAS.get(quality_raw)

    episode = None
    if s.ep_mode == "normal":
        # Normal regex (E01, Ep 01, etc.)
        m = re.search(
            r"(s\d{1,2}e\d{1,4}|episode\s*0*\d{1,4}|ep\.?\s*0*\d{1,4}|\be\s*0*\d{1,4})",
            text,
            re.I
        )
        if m:
            digits = re.findall(r"\d{1,4}", m.group(0))
            if digits:
                episode = int(digits[-1])

    elif s.ep_mode == "001":
        # Look for (039), (040), etc.
        m = re.search(r"\((\d{3,4})\)", text)
        if m:
            episode = int(m.group(1))

    return episode, quality, original


# New function for quality sort video parsing
def parse_quality_video(msg: Message, ep_mode: str = "normal"):
    text = (msg.caption or msg.video.file_name or "").lower()
    
    # Detect quality
    quality_raw = next((q for q in QUALITY_TAGS if q in text), None)
    quality = QUALITY_ALIAS.get(quality_raw)

    episode = None
    if ep_mode == "normal":
        # Normal regex (E01, Ep 01, etc.)
        m = re.search(
            r"(s\d{1,2}e\d{1,4}|episode\s*0*\d{1,4}|ep\.?\s*0*\d{1,4}|\be\s*0*\d{1,4})",
            text,
            re.I
        )
        if m:
            digits = re.findall(r"\d{1,4}", m.group(0))
            if digits:
                episode = int(digits[-1])

    elif s.ep_mode == "001":
        # Look for (039), (040), etc.
        m = re.search(r"\((\d{3,4})\)", text)
        if m:
            episode = int(m.group(1))
        else:
            # Also try to find 3-4 digit numbers directly
            m = re.search(r"\b(\d{3,4})\b", text)
            if m and 1 <= int(m.group(1)) <= 999:
                episode = int(m.group(1))

    return episode, quality


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
        "`/sort` ➜ `/setnames` ➜ `/setformat` ➜ `/setstickers` ➜ `/ignore <anime name>` ➜ `/publish`\n\n"
        "**New Quality Sort:**\n"
        "`/qualitysort` ➜ `/setformatq` ➜ Send episodes ➜ `/publish3`\n\n"
        "⚙️ Use `/epmode` to toggle **episode detection mode** (Normal / 001).",
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
    s.ignore = ""
    s.start_ep = 1  # do not reset ep_mode here
    await m.reply(
        f"✅ Sorting session **{label}** started.\n"
        "Forward videos, then do `/setnames`, `/setformat`, `/setstickers`, `/ignore <anime name>`, `/publish`.",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("setnames") & filters.private)
async def cmd_setnames(_, m: Message):
    titles = [ln.strip() for ln in m.text.split("\n")[1:] if ln.strip()]
    if not titles:
        return await m.reply("❌ Paste episode titles after the command.", quote=True)

    s = users[m.from_user.id]
    s.names = titles

    # Detect starting episode number
    m_num = re.search(r"\d{1,4}", titles[0])
    s.start_ep = int(m_num.group(0)) if m_num else 1

    await m.reply(
        f"✅ Stored **{len(titles)}** episode names.\nStarting episode: **{s.start_ep}**",
        parse_mode=ParseMode.MARKDOWN,
    )


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

    parts = m.text.split()
    if len(parts) == 3:
        s.stickers = parts[1:]
        return await m.reply("✅ Stickers saved via parameters!", quote=True)

    await m.reply(
        "Reply to a sticker with `/setstickers` (do this twice) **or** `/setstickers id1 id2`.",
        quote=True,
    )


@app.on_message(filters.command("ignore") & filters.private)
async def cmd_ignore(_, m: Message):
    text = " ".join(m.command[1:]).strip()
    if not text:
        return await m.reply("❌ Usage: `/ignore <anime name>`", quote=True)
    users[m.from_user.id].ignore = text.lower()
    await m.reply(f"✅ Now ignoring: **{text}**", parse_mode=ParseMode.MARKDOWN)


@app.on_message(filters.command("epmode") & filters.private)
async def cmd_epmode(_, m: Message):
    s = users[m.from_user.id]
    current = s.ep_mode

    normal_btn = "✅ Normal" if current == "normal" else "Normal"
    mode001_btn = "✅ 001 Mode" if current == "001" else "001 Mode"

    buttons = [
        [InlineKeyboardButton(normal_btn, callback_data="epmode_normal"),
         InlineKeyboardButton(mode001_btn, callback_data="epmode_001")]
    ]

    await m.reply("⚙️ **Select Episode Detection Mode**", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^epmode_"))
async def cb_epmode(_, cq: CallbackQuery):
    s = users[cq.from_user.id]
    mode = cq.data.split("_")[1]

    s.ep_mode = mode
    normal_btn = "✅ Normal" if mode == "normal" else "Normal"
    mode001_btn = "✅ 001 Mode" if mode == "001" else "001 Mode"

    buttons = [
        [InlineKeyboardButton(normal_btn, callback_data="epmode_normal"),
         InlineKeyboardButton(mode001_btn, callback_data="epmode_001")]
    ]

    await cq.message.edit_text(
        f"⚙️ **Episode detection mode set to:** `{s.ep_mode.upper()}`",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN
    )
    await cq.answer("Mode updated!")


@app.on_message(filters.video & filters.private)
async def on_video(_, m: Message):
    # Check if quality sort is active
    user_id = m.from_user.id
    if user_id in quality_users and quality_users[user_id].is_active:
        # Handle for quality sort
        qs = quality_users[user_id]
        if not qs.caption_format:
            await m.reply("❌ First set format using `/setformatq`")
            return
            
        ep, quality = parse_quality_video(m, qs.ep_mode)
        if not ep or not quality:
            await m.reply(
                "❌ Could not detect episode number and quality from filename/caption.\n"
                "Make sure it contains both (e.g., 'Episode 01 480p.mkv')"
            )
            return
            
        qs.videos[ep][quality] = m.video.file_id
        await m.reply(
            f"📥 Saved **Episode {ep:02d} • {quality}**",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    
    # Handle for normal sort
    ep, q, original = parse_video(m)
    if not ep or not q:
        return await m.reply(
            "❌ Caption or filename must include episode number and quality (480p / 720p / 1080p).",
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
    start_ep = s.start_ep

    for offset, title in enumerate(s.names):
        ep_num = start_ep + offset
        await safe_call(app.send_message, m.chat.id, f"**{title}**", parse_mode=ParseMode.MARKDOWN)

        for q in ["480p", "720p", "1080p"]:
            if q in s.videos.get(ep_num, {}):
                fid, original_name = s.videos[ep_num][q]
                raw = s.caption_format.format(ep=f"{ep_num:02d}", quality=q)
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


# =============================================================================
# QUALITY SORT FEATURE - NEW COMMANDS
# =============================================================================

@app.on_message(filters.command("qualitysort") & filters.private)
async def cmd_qualitysort(_, m: Message):
    user_id = m.from_user.id
    quality_users[user_id] = QualitySortStore()
    qs = quality_users[user_id]
    qs.is_active = True
    
    await m.reply(
        "🎬 **Quality Sort Session Started!**\n\n"
        "**Next Steps:**\n"
        "1. Set caption format using `/setformatq`\n"
        "2. Send your episodes with quality in filename\n"
        "3. Use `/publish3` when done\n\n"
        "**Example filenames:**\n"
        "• `Episode 01 480p.mkv`\n"
        "• `Anime E02 720p.mp4`\n"
        "• `Show [03] 1080p.mkv`",
        parse_mode=ParseMode.MARKDOWN
    )


@app.on_message(filters.command("setformatq") & filters.private)
async def cmd_setformatq(_, m: Message):
    user_id = m.from_user.id
    if user_id not in quality_users or not quality_users[user_id].is_active:
        return await m.reply("❌ Start a quality sort session with `/qualitysort` first.")
    
    lines = m.text.splitlines()
    if len(lines) < 2:
        return await m.reply(
            "❌ **Please provide format after command:**\n\n"
            "**Example:**\n"
            "`/setformatq`\n"
            "➥ Anime Name [S01]\n"
            "🎬 Episode - {ep}\n"
            "🎧 Language - Hindi #Official\n"
            "🔎 Quality : {quality}\n"
            "📡 Powered by : @CrunchyRollChannel.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    fmt = "\n".join(lines[1:]).strip()
    if "{ep}" not in fmt or "{quality}" not in fmt:
        return await m.reply("❌ Format must include `{ep}` and `{quality}` placeholders.")
    
    quality_users[user_id].caption_format = fmt
    
    await m.reply(
        "✅ **Caption format saved for Quality Sort!**\n\n"
        "Now you can start sending episodes.\n\n"
        "**Make sure filenames include:**\n"
        "• Episode number (E01, Episode 1, etc.)\n"  
        "• Quality (480p, 720p, 1080p)\n\n"
        "Use `/publish3` when done sending all episodes.",
        parse_mode=ParseMode.MARKDOWN
    )


@app.on_message(filters.command("publish3") & filters.private)
async def cmd_publish3(_, m: Message):
    user_id = m.from_user.id
    if user_id not in quality_users or not quality_users[user_id].is_active:
        return await m.reply("❌ Start a quality sort session with `/qualitysort` first.")
    
    qs = quality_users[user_id]
    
    if not qs.caption_format:
        return await m.reply("❌ Set caption format with `/setformatq` first.")
    if not qs.videos:
        return await m.reply("❌ No episodes collected. Send some videos first.")
    
    await m.reply("🚀 **Starting Quality-Wise Publication...**")
    
    try:
        episodes = sorted(qs.videos.keys())
        qualities = ["480p", "720p", "1080p"]
        total_posted = 0
        
        # Publish by quality
        for quality in qualities:
            # Check if we have any episodes in this quality
            has_episodes = False
            for ep in episodes:
                if quality in qs.videos[ep]:
                    has_episodes = True
                    break
            
            if not has_episodes:
                continue
                
            # Send all episodes for this quality
            for episode in episodes:
                if quality in qs.videos[episode]:
                    file_id = qs.videos[episode][quality]
                    raw_caption = qs.caption_format.format(
                        ep=f"{episode:02d}", 
                        quality=quality
                    )
                    # Make entire caption bold
                    caption = "\n".join(f"**{line}**" for line in raw_caption.splitlines())
                    
                    await safe_call(
                        app.send_video,
                        m.chat.id,
                        file_id,
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    total_posted += 1
                    await asyncio.sleep(2)  # Avoid flood wait
        
        # Cleanup session
        del quality_users[user_id]
        
        await m.reply(f"🎉 Posted **{total_posted}** episodes successfully!", parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await m.reply(f"❌ **Error during publication:** `{str(e)}`")


@app.on_message(filters.command("qstatus") & filters.private)
async def cmd_qstatus(_, m: Message):
    user_id = m.from_user.id
    if user_id not in quality_users or not quality_users[user_id].is_active:
        return await m.reply("❌ No active quality sort session. Start with `/qualitysort`")
    
    qs = quality_users[user_id]
    
    # Count videos by quality
    quality_count = {"480p": 0, "720p": 0, "1080p": 0}
    for ep_data in qs.videos.values():
        for quality in ep_data:
            if quality in quality_count:
                quality_count[quality] += 1
    
    status_msg = [
        "📊 **Quality Sort Status**",
        f"✅ **Caption Format:** {'SET' if qs.caption_format else 'NOT SET'}",
        f"📹 **Episodes Collected:** {len(qs.videos)}",
        f"⚙️ **Episode Mode:** {qs.ep_mode.upper()}",
        "",
        "**Videos by Quality:**",
        f"• 480p: {quality_count['480p']}",
        f"• 720p: {quality_count['720p']}", 
        f"• 1080p: {quality_count['1080p']}",
        "",
        "**Next:** Send more episodes or use `/publish3`"
    ]
    
    await m.reply("\n".join(status_msg))


@app.on_message(filters.command("qcancel") & filters.private)
async def cmd_qcancel(_, m: Message):
    user_id = m.from_user.id
    if user_id in quality_users:
        del quality_users[user_id]
        await m.reply("✅ Quality sort session cancelled.")
    else:
        await m.reply("❌ No active quality sort session.")


app.run()
