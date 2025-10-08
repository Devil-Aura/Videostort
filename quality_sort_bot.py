import asyncio
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any

from pyrogram import Client, filters
from pyrogram.enums import ParseMode, MessageMediaType
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
        self.waiting_for_powered_by: bool = False
        self.waiting_for_format: bool = False


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
            if m and 1 <= int(m.group(1)) <= 999:
                episode = int(m.group(1))
    
    return episode, quality


async def safe_call(func, *args, **kwargs):
    """Safe call with flood wait handling"""
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)


def is_command(text: str) -> bool:
    """Check if text is a command"""
    return text and text.startswith('/')


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
        session.waiting_for_powered_by = True
        
        await m.reply(
            "🎬 **Quality Sort Session Started**\n\n"
            "📝 **Step 1/3:** Please send the **Powered By Post** (the message you want to include at the beginning)\n\n"
            "_This can be any message - text, photo, video, or document with caption_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="q_cancel")
            ]])
        )

    @app.on_message(filters.command("setformatq") & filters.private)
    async def cmd_setformatq(_, m: Message):
        """Set caption format for quality sort"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return await m.reply("❌ Start a session with `/qualitysort` first.")
        
        session = quality_sessions[user_id]
        
        if not session.powered_by_post:
            return await m.reply("❌ Please send the Powered By post first.")
        
        lines = m.text.splitlines()
        if len(lines) < 2:
            return await m.reply(
                "❌ **Please provide format after command:**\n\n"
                "**Example:**\n"
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
        
        session.caption_format = fmt
        session.waiting_for_format = False
        
        await m.reply(
            "✅ **Caption format saved!**\n\n"
            "**Step 3/3:** Now you can start sending episodes.\n\n"
            "**Make sure filenames include:**\n"
            "• Episode number (E01, Episode 1, etc.)\n"  
            "• Quality (480p, 720p, 1080p)\n\n"
            "**When done, use:** `/publishq`\n"
            "**Check status:** `/statusq`\n"
            "**Cancel:** `/cancelq`",
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
            InlineKeyboardButton(mode001_btn, callback_data="q_epmode_001")],
            [InlineKeyboardButton("❌ Cancel", callback_data="q_cancel")]
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
            await cq.answer("Session expired. Start with /qualitysort", show_alert=True)
            return
        
        session = quality_sessions[user_id]
        mode = cq.data.split("_")[2]
        session.ep_mode = mode
        
        normal_btn = "✅ Normal" if mode == "normal" else "Normal"
        mode001_btn = "✅ 001 Mode" if mode == "001" else "001 Mode"

        buttons = [
            [InlineKeyboardButton(normal_btn, callback_data="q_epmode_normal"),
            [InlineKeyboardButton(mode001_btn, callback_data="q_epmode_001")],
            [InlineKeyboardButton("❌ Cancel", callback_data="q_cancel")]
        ]

        await cq.message.edit_text(
            f"⚙️ **Episode detection mode set to:** `{mode.upper()}`",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        await cq.answer("Mode updated!")

    @app.on_callback_query(filters.regex("^q_cancel$"))
    async def cb_q_cancel(_, cq):
        """Handle cancel callback"""
        user_id = cq.from_user.id
        if user_id in quality_sessions:
            del quality_sessions[user_id]
        await cq.message.edit_text("❌ **Quality sort session cancelled.**")
        await cq.answer()

    @app.on_callback_query(filters.regex("^q_set_format$"))
    async def cb_q_set_format(_, cq):
        """Handle set format callback"""
        await cq.message.reply(
            "📝 **Set Caption Format:**\n\n"
            "Use this command with your format:\n\n"
            "```/setformatq\n➥ Anime Name [S02]\n🎬 Episode - {ep}\n🎧 Language - Hindi #Official\n🔎 Quality : {quality}\n📡 Powered by : @CrunchyRollChannel```\n\n"
            "**Important:** Keep `{ep}` and `{quality}` in your format!",
            parse_mode=ParseMode.MARKDOWN
        )
        await cq.answer()

    # Handle non-command messages for powered by post
    @app.on_message(filters.private & filters.text)
    async def handle_text_messages(_, m: Message):
        """Handle text messages for powered by post"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return
        
        session = quality_sessions[user_id]
        
        # Skip if this is a command
        if m.text and m.text.startswith('/'):
            return
            
        # Handle powered by post
        if session.waiting_for_powered_by:
            session.powered_by_post = m
            session.waiting_for_powered_by = False
            session.waiting_for_format = True
            
            await m.reply(
                "✅ **Powered By Post Saved!**\n\n"
                "**Step 2/3:** Now set the caption format using:\n\n"
                "`/setformatq`\n"
                "➥ Anime Name [S02]\n"
                "🎬 Episode - {ep}\n"
                "🎧 Language - Hindi #Official\n"
                "🔎 Quality : {quality}\n"
                "📡 Powered by : @CrunchyRollChannel\n\n"
                "_Replace with your actual format_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Set Format Now", callback_data="q_set_format")
                ]])
            )

    # Handle media messages for powered by post and videos
    @app.on_message(filters.private & (filters.photo | filters.video | filters.document))
    async def handle_media_messages(_, m: Message):
        """Handle media messages for powered by post and videos"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return
        
        session = quality_sessions[user_id]
        
        # Handle powered by post (any media message when waiting for it)
        if session.waiting_for_powered_by:
            session.powered_by_post = m
            session.waiting_for_powered_by = False
            session.waiting_for_format = True
            
            await m.reply(
                "✅ **Powered By Post Saved!**\n\n"
                "**Step 2/3:** Now set the caption format using:\n\n"
                "`/setformatq`\n"
                "➥ Anime Name [S02]\n"
                "🎬 Episode - {ep}\n"
                "🎧 Language - Hindi #Official\n"
                "🔎 Quality : {quality}\n"
                "📡 Powered by : @CrunchyRollChannel\n\n"
                "_Replace with your actual format_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Set Format Now", callback_data="q_set_format")
                ]])
            )
            return
        
        # Handle videos for episode collection
        if m.video and session.caption_format:
            text = (m.caption or m.video.file_name or "").lower()
            episode, quality = parse_episode_quality(text, session.ep_mode)
            
            if not episode:
                await m.reply("❌ **Could not detect episode number!**\n\nMake sure filename/caption contains episode number (E01, Episode 1, etc.)")
                return
                
            if not quality:
                await m.reply("❌ **Could not detect quality!**\n\nMake sure filename/caption contains quality (480p, 720p, 1080p)")
                return
            
            # Store video
            session.videos[episode][quality] = m.video.file_id
            
            # Store episode name if available
            if m.caption:
                session.episode_names[episode] = m.caption.split('\n')[0]
            
            episode_count = len(session.videos)
            await m.reply(
                f"✅ **Episode Saved Successfully!**\n\n"
                f"**Episode:** {episode:03d}\n"
                f"**Quality:** {quality}\n"
                f"**Total Episodes:** {episode_count}\n\n"
                f"Continue sending episodes or use `/publishq` when done.",
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
            return await m.reply("❌ Please send the Powered By post first.")
        if not session.caption_format:
            return await m.reply("❌ Set caption format with `/setformatq` first.")
        if not session.videos:
            return await m.reply("❌ No episodes collected. Send some videos first.")
        
        await m.reply("🚀 **Starting publication process...**\n\nThis may take a while depending on the number of episodes.")
        
        try:
            total_episodes = len(session.videos)
            posted_count = 0
            
            # Send powered by post first (forward as is)
            if session.powered_by_post:
                await safe_call(
                    app.copy_message,
                    m.chat.id,
                    session.powered_by_post.chat.id,
                    session.powered_by_post.id
                )
                await asyncio.sleep(2)
            
            # Get all episodes and sort them
            episodes = sorted(session.videos.keys())
            qualities = ["480p", "720p", "1080p"]
            
            # Process by quality first
            for quality in qualities:
                has_episodes_in_quality = any(quality in session.videos[ep] for ep in episodes)
                
                if not has_episodes_in_quality:
                    continue
                
                # Send broader sticker
                await safe_call(app.send_sticker, m.chat.id, BROADER_STICKER)
                await asyncio.sleep(1)
                
                # Send quality sticker
                if quality in QUALITY_STICKERS:
                    await safe_call(app.send_sticker, m.chat.id, QUALITY_STICKERS[quality])
                    await asyncio.sleep(1)
                
                # Send all episodes for this quality
                for episode in episodes:
                    if quality in session.videos[episode]:
                        file_id = session.videos[episode][quality]
                        caption = session.caption_format.format(
                            ep=f"{episode:03d}", 
                            quality=quality
                        )
                        
                        await safe_call(
                            app.send_video,
                            m.chat.id,
                            file_id,
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        posted_count += 1
                        await asyncio.sleep(2)  # Avoid flood wait
            
            # Send final stickers
            await safe_call(app.send_sticker, m.chat.id, BROADER_STICKER)
            await asyncio.sleep(1)
            await safe_call(app.send_sticker, m.chat.id, END_SEASON_STICKER)
            
            # Cleanup session
            if user_id in quality_sessions:
                del quality_sessions[user_id]
            
            await m.reply(
                f"✅ **Publication Complete!**\n\n"
                f"**Total Episodes Processed:** {total_episodes}\n"
                f"**Total Videos Posted:** {posted_count}\n"
                f"**Qualities:** 480p, 720p, 1080p\n\n"
                f"Use `/qualitysort` to start a new session."
            )
            
        except Exception as e:
            await m.reply(f"❌ **Error during publication:** `{str(e)}`\n\nSession preserved. You can try again.")

    @app.on_message(filters.command("cancelq") & filters.private)
    async def cmd_cancelq(_, m: Message):
        """Cancel quality sort session"""
        user_id = m.from_user.id
        if user_id in quality_sessions:
            del quality_sessions[user_id]
            await m.reply("❌ **Quality sort session cancelled.**")
        else:
            await m.reply("❌ No active quality sort session.")

    @app.on_message(filters.command("statusq") & filters.private)
    async def cmd_statusq(_, m: Message):
        """Check quality sort session status"""
        user_id = m.from_user.id
        if user_id not in quality_sessions or not quality_sessions[user_id].is_active:
            return await m.reply("❌ No active quality sort session. Start with `/qualitysort`")
        
        session = quality_sessions[user_id]
        
        # Count videos by quality
        quality_count = {"480p": 0, "720p": 0, "1080p": 0}
        for ep_data in session.videos.values():
            for quality in ep_data:
                if quality in quality_count:
                    quality_count[quality] += 1
        
        status_msg = [
            "📊 **Quality Sort Session Status**",
            f"✅ **Powered By Post:** {'✅ Set' if session.powered_by_post else '❌ Not Set'}",
            f"✅ **Caption Format:** {'✅ Set' if session.caption_format else '❌ Not Set'}",
            f"📹 **Episodes Collected:** {len(session.videos)}",
            f"⚙️ **Episode Mode:** {session.ep_mode.upper()}",
            "",
            "**Videos by Quality:**",
            f"• 480p: {quality_count['480p']} episodes",
            f"• 720p: {quality_count['720p']} episodes", 
            f"• 1080p: {quality_count['1080p']} episodes",
            "",
            "**Next Steps:**",
        ]
        
        if not session.powered_by_post:
            status_msg.append("• Send the Powered By post")
        elif not session.caption_format:
            status_msg.append("• Use `/setformatq` to set caption format")
        else:
            status_msg.append("• Send more episodes or use `/publishq` when ready")
        
        status_msg.extend([
            "",
            "**Commands:**",
            "• `/publishq` - Publish all episodes", 
            "• `/epmodeq` - Change episode detection",
            "• `/cancelq` - Cancel session"
        ])
        
        await m.reply("\n".join(status_msg), parse_mode=ParseMode.MARKDOWN)
