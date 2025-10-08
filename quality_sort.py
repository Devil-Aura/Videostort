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


class QualitySortSession:
    def __init__(self):
        self.powered_by_post: Optional[Message] = None
        self.caption_format: str = ""
        self.videos: Dict[int, Dict[str, str]] = defaultdict(dict)  # {ep: {quality: file_id}}
        self.episode_names: Dict[int, str] = {}
        self.is_active: bool = False
        self.ep_mode: str = "normal"  # normal or 001


quality_sessions: Dict[int, QualitySortSession] = {}


def parse_episode_quality(text: str, ep_mode: str = "normal") -> Tuple[Optional[int], Optional[str]]:
    """Parse episode number and quality from text"""
    text = text.lower()
    
    # Detect quality
    quality_raw = next((q for q in QUALITY_TAGS if q in text), None)
    quality = QUALITY_ALIAS.get(quality_raw)
    
    episode = None
    
    if ep_mode == "normal":
        # Normal episode detection (E01, Ep 01, etc.)
        m = re.search(
            r"(s\d{1,2}e\d{1,4}|episode\s*0*\d{1,4}|ep\.?\s*0*\d{1,4}|\be\s*0*\d{1,4})",
            text,
            re.I
        )
        if m:
            digits = re.findall(r"\d{1,4}", m.group(0))
            if digits:
                episode = int(digits[-1])
                
    elif ep_mode == "001":
        # 001 mode detection (001, 002, etc.)
        m = re.search(r"\((\d{3,4})\)", text)
        if m:
            episode = int(m.group(1))
        else:
            # Also try to find 3-4 digit numbers
            m = re.search(r"\b(\d{3,4})\b", text)
            if m:
                episode = int(m.group(1))
    
    return episode, quality


async def safe_call(func, *args, **kwargs):
    """Safe call with flood wait handling"""
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)


def setup_quality_sort_handlers(app: Client):
    """Setup all quality sort handlers"""
    
    @app.on_message(filters.command("qualitysort") & filters.private)
    async def cmd_qualitysort(_, m: Message):
        """Start quality sort session"""
        user_id = m.from_user.id
        
        # Initialize or reset session
        quality_sessions[user_id] = QualitySortSession()
        session = quality_sessions[user_id]
        session.is_active = True
        
        await m.reply(
            "🎬 **Quality Sort Session Started**\n\n"
            "📝 **Next Steps:**\n"
            "1. Send the **Powered By Post** (the message you want to include at start)\n"
            "2. Use `/setformatq` to set caption format\n"
            "3. Send your episodes with quality tags (480p, 720p, 1080p)\n"
            "4. Use `/publishq` when done\n\n"
            "⚙️ Use `/epmodeq` to change episode detection mode",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Set Format", callback_data="set_format_q")
            ]])
        )

    @app.on_message(filters.command("setformatq") & filters.private)
    async def cmd_setformatq(_, m: Message):
        """Set caption format for quality sort"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return await m.reply("❌ Start a session with `/qualitysort` first.")
        
        lines = m.text.splitlines()
        if len(lines) < 2:
            return await m.reply(
                "❌ Please provide format after command:\n"
                "`/setformatq`\n"
                "➥ Anime Name [S02]\n"
                "🎬 Episode - {ep}\n"
                "🎧 Language - Hindi #Official\n"
                "🔎 Quality : {quality}\n"
                "📡 Powered by : @CrunchyRollChannel",
                parse_mode=ParseMode.MARKDOWN
            )
        
        fmt = "\n".join(lines[1:]).strip()
        if "{ep}" not in fmt or "{quality}" not in fmt:
            return await m.reply("❌ Format must include `{ep}` and `{quality}` placeholders.")
        
        quality_sessions[user_id].caption_format = fmt
        await m.reply(
            "✅ **Caption format saved!**\n\n"
            "Now you can start sending episodes. Make sure filenames include:\n"
            "• Episode number (E01, Episode 1, etc.)\n"  
            "• Quality (480p, 720p, 1080p)\n\n"
            "Use `/publishq` when done.",
            parse_mode=ParseMode.MARKDOWN
        )

    @app.on_message(filters.command("epmodeq") & filters.private)
    async def cmd_epmodeq(_, m: Message):
        """Set episode mode for quality sort"""
        user_id = m.from_user.id
        if user_id not in quality_sessions:
            return await m.reply("❌ Start a session with `/qualitysort` first.")
        
        session = quality_sessions[user_id]
        current = session.ep_mode

        normal_btn = "✅ Normal" if current == "normal" else "Normal"
        mode001_btn = "✅ 001 Mode" if current == "001" else "001 Mode"

        buttons = [
            [InlineKeyboardButton(normal_btn, callback_data="q_epmode_normal"),
            InlineKeyboardButton(mode001_btn, callback_data="q_epmode_001")]
        ]

        await m.reply(
            "⚙️ **Select Episode Detection Mode**\n\n"
            "• **Normal**: E01, Episode 1, Ep 01\n"
            "• **001 Mode**: 001, 002, (001), (002)",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    @app.on_callback_query(filters.regex(r"^q_epmode_"))
    async def cb_q_epmode(_, cq):
        """Handle episode mode callback"""
        user_id = cq.from_user.id
        if user_id not in quality_sessions:
            await cq.answer("Session expired. Start with /qualitysort")
            return
        
        session = quality_sessions[user_id]
        mode = cq.data.split("_")[2]
        session.ep_mode = mode
        
        normal_btn = "✅ Normal" if mode == "normal" else "Normal"
        mode001_btn = "✅ 001 Mode" if mode == "001" else "001 Mode"

        buttons = [
            [InlineKeyboardButton(normal_btn, callback_data="q_epmode_normal"),
            InlineKeyboardButton(mode001_btn, callback_data="q_epmode_001")]
        ]

        await cq.message.edit_text(
            f"⚙️ **Episode detection mode set to:** `{mode.upper()}`",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await cq.answer("Mode updated!")

    @app.on_callback_query(filters.regex("^set_format_q$"))
    async def cb_set_format_q(_, cq):
        """Handle set format callback"""
        await cq.message.reply(
            "📝 **Set Caption Format:**\n\n"
            "Use `/setformatq` followed by your format:\n"
            "```/setformatq\n➥ Anime Name [S02]\n🎬 Episode - {ep}\n🎧 Language - Hindi #Official\n🔎 Quality : {quality}\n📡 Powered by : @CrunchyRollChannel```",
            parse_mode=ParseMode.MARKDOWN
        )
        await cq.answer()

    @app.on_message(filters.private & ~filters.command & filters.text)
    async def handle_powered_by_post(_, m: Message):
        """Handle powered by post"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return
        
        session = quality_sessions[user_id]
        
        # If powered by post not set and this is not a command
        if not session.powered_by_post and not m.text.startswith('/'):
            session.powered_by_post = m
            await m.reply(
                "✅ **Powered By Post Saved!**\n\n"
                "Now set the caption format using `/setformatq`",
                parse_mode=ParseMode.MARKDOWN
            )

    @app.on_message(filters.video & filters.private)
    async def handle_quality_video(_, m: Message):
        """Handle video messages for quality sort"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return
        
        session = quality_sessions[user_id]
        
        if not session.caption_format:
            await m.reply("❌ Set caption format first with `/setformatq`")
            return
        
        text = (m.caption or m.video.file_name or "").lower()
        episode, quality = parse_episode_quality(text, session.ep_mode)
        
        if not episode:
            await m.reply("❌ Could not detect episode number from filename/caption")
            return
            
        if not quality:
            await m.reply("❌ Could not detect quality (480p/720p/1080p) from filename/caption")
            return
        
        # Store video
        session.videos[episode][quality] = m.video.file_id
        
        # Store episode name if available
        if m.caption:
            session.episode_names[episode] = m.caption.split('\n')[0]
        
        await m.reply(
            f"✅ **Saved**\n"
            f"**Episode:** {episode:02d}\n"
            f"**Quality:** {quality}\n"
            f"**Total episodes:** {len(session.videos)}",
            parse_mode=ParseMode.MARKDOWN
        )

    @app.on_message(filters.command("publishq") & filters.private)
    async def cmd_publishq(_, m: Message):
        """Publish quality sorted episodes"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return await m.reply("❌ Start a session with `/qualitysort` first.")
        
        session = quality_sessions[user_id]
        
        # Validate session
        if not session.powered_by_post:
            return await m.reply("❌ Send the Powered By post first.")
        if not session.caption_format:
            return await m.reply("❌ Set caption format with `/setformatq` first.")
        if not session.videos:
            return await m.reply("❌ No episodes collected. Send some videos first.")
        
        await m.reply("🚀 Starting publication...")
        
        try:
            # Send powered by post first (forward as is)
            if session.powered_by_post:
                await safe_call(
                    app.copy_message,
                    m.chat.id,
                    session.powered_by_post.chat.id,
                    session.powered_by_post.id
                )
                await asyncio.sleep(1)
            
            # Get all episodes and sort them
            episodes = sorted(session.videos.keys())
            qualities = ["480p", "720p", "1080p"]
            
            # Process by quality first
            for quality in qualities:
                # Send broader sticker
                await safe_call(app.send_sticker, m.chat.id, BROADER_STICKER)
                await asyncio.sleep(0.5)
                
                # Send quality sticker
                if quality in QUALITY_STICKERS:
                    await safe_call(app.send_sticker, m.chat.id, QUALITY_STICKERS[quality])
                    await asyncio.sleep(0.5)
                
                # Send all episodes for this quality
                for episode in episodes:
                    if quality in session.videos[episode]:
                        file_id = session.videos[episode][quality]
                        caption = session.caption_format.format(
                            ep=f"{episode:02d}", 
                            quality=quality
                        )
                        
                        await safe_call(
                            app.send_video,
                            m.chat.id,
                            file_id,
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        await asyncio.sleep(1)
                
                await asyncio.sleep(1)
            
            # Send broader sticker
            await safe_call(app.send_sticker, m.chat.id, BROADER_STICKER)
            await asyncio.sleep(0.5)
            
            # Send end season sticker
            await safe_call(app.send_sticker, m.chat.id, END_SEASON_STICKER)
            
            await m.reply(f"✅ **Publication Complete!**\nPosted {len(episodes)} episodes in all qualities.")
            
        except Exception as e:
            await m.reply(f"❌ Error during publication: {str(e)}")
        
        finally:
            # Cleanup session
            if user_id in quality_sessions:
                del quality_sessions[user_id]

    @app.on_message(filters.command("cancelq") & filters.private)
    async def cmd_cancelq(_, m: Message):
        """Cancel quality sort session"""
        user_id = m.from_user.id
        if user_id in quality_sessions:
            del quality_sessions[user_id]
            await m.reply("❌ Quality sort session cancelled.")
        else:
            await m.reply("❌ No active quality sort session.")

    @app.on_message(filters.command("statusq") & filters.private)
    async def cmd_statusq(_, m: Message):
        """Check quality sort session status"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return await m.reply("❌ No active quality sort session.")
        
        session = quality_sessions[user_id]
        status_msg = [
            "📊 **Quality Sort Session Status**",
            f"✅ Powered By Post: {'Set' if session.powered_by_post else 'Not Set'}",
            f"✅ Caption Format: {'Set' if session.caption_format else 'Not Set'}",
            f"📹 Episodes Collected: {len(session.videos)}",
            f"⚙️ Episode Mode: {session.ep_mode.upper()}",
            "",
            "**Next Steps:**",
            "• Send more episodes" if not session.powered_by_post else "",
            "• Set format with `/setformatq`" if not session.caption_format else "",
            "• Use `/publishq` when ready" if session.powered_by_post and session.caption_format else "",
        ]
        
        await m.reply("\n".join(filter(None, status_msg)), parse_mode=ParseMode.MARKDOWN)
