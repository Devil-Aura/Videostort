import asyncio
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# Quality stickers
BROADER_STICKER = "CAACAgUAAxkBAAEPiYto5msZJApY_TqYnam4BvgeUFJiwwACyQwAAqbimVUBY5iDB0EIOzYE"
QUALITY_480_STICKER = "CAACAgUAAxkBAAEPiY9o5mtoWel0eDiKJbDvp3LDtk1QxwAC3Q4AAmoHKVRzXVzL8oQItjYE"
QUALITY_720_STICKER = "CAACAgUAAxkBAAEPiZBo5mtptlgsq3liZG6m7PpYyASNtAACGw8AAupbKVST-KQXiWXU1TYE"
QUALITY_1080_STICKER = "CAACAgUAAxkBAAEPiZJo5mtqhRL6Gv8QPvSJ-VFwSPgvsgAC2g0AAsmaKVRz8GmG5KkbGjYE"
END_SEASON_STICKER = "CAACAgUAAxkBAAEPhsto475lLcwuynonRnqiajcaCxPDKQAC0w8AAmxwKFSRq2AOacBIWzYE"

QUALITY_STICKERS = {
    "480p": QUALITY_480_STICKER,
    "720p": QUALITY_720_STICKER, 
    "1080p": QUALITY_1080_STICKER
}

class QualitySortSession:
    def __init__(self):
        self.powered_by_post = None
        self.caption_format = ""
        self.videos = defaultdict(dict)  # {ep: {quality: file_id}}
        self.is_active = False
        self.ep_mode = "normal"

quality_sessions = {}

async def safe_call(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)

def parse_episode_quality(text: str, ep_mode: str = "normal"):
    """Parse episode number and quality from text"""
    if not text:
        return None, None
        
    text = text.lower()
    
    # Detect quality
    quality = None
    for q in ["480p", "720p", "1080p"]:
        if q in text:
            quality = q
            break
    
    # Detect episode
    episode = None
    
    if ep_mode == "normal":
        # Try different patterns
        patterns = [
            r'e\s*(\d{1,3})',
            r'ep\s*(\d{1,3})', 
            r'episode\s*(\d{1,3})',
            r'\.(\d{1,3})\.',
            r'\[(\d{1,3})\]',
            r'\((\d{1,3})\)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                episode = int(match.group(1))
                break
                
    elif ep_mode == "001":
        # Look for 3-digit numbers
        match = re.search(r'(\d{3})', text)
        if match:
            episode = int(match.group(1))
    
    return episode, quality

def setup_quality_sort_handlers(app: Client):
    
    @app.on_message(filters.command("qualitysort") & filters.private)
    async def cmd_qualitysort(_, m: Message):
        user_id = m.from_user.id
        quality_sessions[user_id] = QualitySortSession()
        session = quality_sessions[user_id]
        session.is_active = True
        
        await m.reply(
            "🎬 **Quality Sort Started!**\n\n"
            "**Step 1:** Send the **Powered By Post** (any message you want at the start)\n\n"
            "This can be text, photo, video - anything!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="q_cancel")
            ]])
        )

    @app.on_message(filters.command("setformatq") & filters.private)
    async def cmd_setformatq(_, m: Message):
        user_id = m.from_user.id
        if user_id not in quality_sessions:
            return await m.reply("❌ Start with `/qualitysort` first")
            
        session = quality_sessions[user_id]
        
        if not session.powered_by_post:
            return await m.reply("❌ Send Powered By post first!")
        
        # Extract format from command
        if not m.text or "\n" not in m.text:
            return await m.reply(
                "❌ **Send format like this:**\n\n"
                "`/setformatq`\n"
                "➥ Anime Name\n"
                "🎬 Episode {ep}\n" 
                "🔊 Hindi\n"
                "📺 {quality}\n"
                "📡 @ChannelName"
            )
        
        fmt = m.text.split('\n', 1)[1].strip()
        
        if "{ep}" not in fmt or "{quality}" not in fmt:
            return await m.reply("❌ Include `{ep}` and `{quality}` in format!")
        
        session.caption_format = fmt
        
        await m.reply(
            f"✅ **Format Set!**\n\n"
            f"Now send videos with names like:\n"
            f"• `Episode 01 480p.mkv`\n" 
            f"• `Anime E02 720p.mp4`\n"
            f"• `Show [03] 1080p.mkv`\n\n"
            f"Use `/publishq` when done!\n"
            f"Use `/statusq` to check progress"
        )

    @app.on_message(filters.command("epmodeq") & filters.private)
    async def cmd_epmodeq(_, m: Message):
        user_id = m.from_user.id
        if user_id not in quality_sessions:
            return await m.reply("❌ Start with `/qualitysort` first")
            
        session = quality_sessions[user_id]
        current = session.ep_mode

        buttons = [
            [
                InlineKeyboardButton("✅ Normal" if current == "normal" else "Normal", callback_data="q_epmode_normal"),
                InlineKeyboardButton("✅ 001" if current == "001" else "001", callback_data="q_epmode_001")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="q_cancel")]
        ]

        await m.reply(
            "**Episode Detection Mode:**\n\n"
            "• **Normal**: E01, Episode 1, Ep 01\n" 
            "• **001**: 001, 002, 003",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @app.on_callback_query(filters.regex(r"^q_epmode_"))
    async def cb_epmode(_, cq):
        user_id = cq.from_user.id
        if user_id not in quality_sessions:
            return await cq.answer("Session expired!", show_alert=True)
            
        mode = cq.data.split("_")[2]
        quality_sessions[user_id].ep_mode = mode
        
        buttons = [
            [
                InlineKeyboardButton("✅ Normal" if mode == "normal" else "Normal", callback_data="q_epmode_normal"),
                InlineKeyboardButton("✅ 001" if mode == "001" else "001", callback_data="q_epmode_001")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="q_cancel")]
        ]
        
        await cq.message.edit_text(
            f"✅ Mode set to: **{mode.upper()}**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await cq.answer()

    @app.on_callback_query(filters.regex("^q_cancel$"))
    async def cb_cancel(_, cq):
        user_id = cq.from_user.id
        if user_id in quality_sessions:
            del quality_sessions[user_id]
        await cq.message.edit_text("❌ Session cancelled")
        await cq.answer()

    @app.on_message(filters.private & (filters.text | filters.photo | filters.video | filters.document))
    async def handle_messages(_, m: Message):
        user_id = m.from_user.id
        if user_id not in quality_sessions:
            return
            
        session = quality_sessions[user_id]
        
        # Handle powered by post
        if not session.powered_by_post and not m.text.startswith('/'):
            session.powered_by_post = m
            await m.reply(
                "✅ **Powered By Post Saved!**\n\n"
                "Now set caption format with:\n"
                "`/setformatq`\n"
                "➥ Anime Name\n" 
                "🎬 Episode {ep}\n"
                "🔊 Hindi\n"
                "📺 {quality}\n"
                "📡 @ChannelName"
            )
            return
            
        # Handle videos
        if m.video and session.caption_format:
            text = (m.caption or m.video.file_name or "").strip()
            episode, quality = parse_episode_quality(text, session.ep_mode)
            
            await m.reply(f"🔍 **Debug:** Text='{text}', Episode={episode}, Quality={quality}")
            
            if not episode:
                return await m.reply("❌ Couldn't find episode number!")
            if not quality:
                return await m.reply("❌ Couldn't find quality (480p/720p/1080p)!")
                
            session.videos[episode][quality] = m.video.file_id
            
            count = len(session.videos)
            await m.reply(f"✅ Saved E{episode:02d} {quality}\nTotal: {count} episodes")

    @app.on_message(filters.command("publishq") & filters.private)
    async def cmd_publishq(_, m: Message):
        user_id = m.from_user.id
        if user_id not in quality_sessions:
            return await m.reply("❌ Start with `/qualitysort` first")
            
        session = quality_sessions[user_id]
        
        # Validate
        errors = []
        if not session.powered_by_post:
            errors.append("❌ No Powered By post")
        if not session.caption_format:
            errors.append("❌ No caption format")
        if not session.videos:
            errors.append("❌ No videos collected")
            
        if errors:
            return await m.reply("\n".join(errors))
        
        await m.reply(f"🚀 **Starting publication...**\nFound {len(session.videos)} episodes")
        
        try:
            # Send powered by post
            if session.powered_by_post:
                await safe_call(
                    app.copy_message,
                    m.chat.id,
                    session.powered_by_post.chat.id,
                    session.powered_by_post.id
                )
                await asyncio.sleep(2)
            
            episodes = sorted(session.videos.keys())
            qualities = ["480p", "720p", "1080p"]
            total_posted = 0
            
            for quality in qualities:
                # Check if we have any episodes in this quality
                has_quality = False
                for ep in episodes:
                    if quality in session.videos[ep]:
                        has_quality = True
                        break
                
                if not has_quality:
                    continue
                    
                # Send stickers
                await safe_call(app.send_sticker, m.chat.id, BROADER_STICKER)
                await asyncio.sleep(1)
                await safe_call(app.send_sticker, m.chat.id, QUALITY_STICKERS[quality])
                await asyncio.sleep(1)
                
                # Send episodes for this quality
                for ep in episodes:
                    if quality in session.videos[ep]:
                        file_id = session.videos[ep][quality]
                        caption = session.caption_format.format(ep=f"{ep:02d}", quality=quality)
                        
                        await safe_call(
                            app.send_video,
                            m.chat.id,
                            file_id,
                            caption=caption
                        )
                        total_posted += 1
                        await asyncio.sleep(2)
            
            # End stickers
            await safe_call(app.send_sticker, m.chat.id, BROADER_STICKER)
            await asyncio.sleep(1)
            await safe_call(app.send_sticker, m.chat.id, END_SEASON_STICKER)
            
            # Cleanup
            del quality_sessions[user_id]
            
            await m.reply(f"✅ **Done!** Published {total_posted} videos")
            
        except Exception as e:
            await m.reply(f"❌ Error: {str(e)}")

    @app.on_message(filters.command("statusq") & filters.private)
    async def cmd_statusq(_, m: Message):
        user_id = m.from_user.id
        if user_id not in quality_sessions:
            return await m.reply("❌ No active session")
            
        session = quality_sessions[user_id]
        
        status = [
            "📊 **Session Status**",
            f"✅ Powered By: {'SET' if session.powered_by_post else 'NOT SET'}",
            f"✅ Format: {'SET' if session.caption_format else 'NOT SET'}",
            f"📹 Episodes: {len(session.videos)}",
            f"⚙️ Mode: {session.ep_mode.upper()}"
        ]
        
        # Count by quality
        counts = {"480p": 0, "720p": 0, "1080p": 0}
        for ep_data in session.videos.values():
            for q in ep_data:
                if q in counts:
                    counts[q] += 1
        
        status.extend([
            f"• 480p: {counts['480p']}",
            f"• 720p: {counts['720p']}",
            f"• 1080p: {counts['1080p']}"
        ])
        
        await m.reply("\n".join(status))

    @app.on_message(filters.command("cancelq") & filters.private)
    async def cmd_cancelq(_, m: Message):
        user_id = m.from_user.id
        if user_id in quality_sessions:
            del quality_sessions[user_id]
            await m.reply("✅ Session cancelled")
        else:
            await m.reply("❌ No active session")
