import os
import re
import glob
import asyncio
from pathlib import Path
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

BOT_TOKEN = os.getenv("BOT_TOKEN", "9280771787:AAGKrgffYGOEmHBxR4IF9RZPjj_8D8nyDcc")
ALLOWED_CHAT_ID = os.getenv("CHAT_ID", "-5155020880")  # sodo-player group

TEMP_DIR = Path("./temp_downloads")
TEMP_DIR.mkdir(exist_ok=True)

YOUTUBE_REGEX = r'(https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+)'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text:
        return

    text = update.effective_message.text
    chat_id = str(update.effective_chat.id)

    # Optional: only respond in your target group or private chat
    if ALLOWED_CHAT_ID and chat_id != str(ALLOWED_CHAT_ID):
        # Ignore messages outside the group
        return

    match = re.search(YOUTUBE_REGEX, text)
    if not match:
        return

    url = match.group(0)
    status_msg = await update.effective_message.reply_text("⏳ Detected YouTube link! Downloading video...", quote=True)

    task_id = f"vps_{int(asyncio.get_event_loop().time() * 1000)}"
    out_tmpl = str(TEMP_DIR / f"{task_id}_%(title).80s.%(ext)s")

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': out_tmpl,
        'writethumbnail': True,
        'quiet': True,
        'no_warnings': True,
    }

    loop = asyncio.get_event_loop()
    def download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)

    try:
        info = await loop.run_in_executor(None, download)
        title = info.get('title', 'Archived Video')
        uploader = info.get('uploader', 'Unknown Channel')

        video_file = None
        thumb_file = None
        for f in TEMP_DIR.glob(f"{task_id}_*"):
            if f.suffix.lower() in ('.mp4', '.mkv', '.webm'):
                video_file = f
            elif f.suffix.lower() in ('.jpg', '.jpeg', '.webp', '.png'):
                thumb_file = f

        if not video_file or not video_file.exists():
            await status_msg.edit_text("❌ Failed to download video.")
            return

        size_mb = video_file.stat().st_size / (1024 * 1024)
        if size_mb > 50:
            await status_msg.edit_text(f"⚠️ Video is {size_mb:.1f} MB, which exceeds Telegram's 50 MB standard bot API limit.")
            return

        await status_msg.edit_text("📤 Uploading video & document to group...")

        caption = f"🎥 *{title}*\n👤 {uploader}\n🔗 [Original Link]({url})"

        # 1. Send as Video
        with open(video_file, "rb") as vf:
            thumb = open(thumb_file, "rb") if thumb_file and thumb_file.exists() else None
            try:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=vf,
                    thumbnail=thumb,
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True
                )
            finally:
                if thumb:
                    thumb.close()

        # 2. Send as Document
        with open(video_file, "rb") as df:
            await context.bot.send_document(
                chat_id=chat_id,
                document=df,
                caption=f"📁 *Document Archive*\n{title}",
                parse_mode="Markdown"
            )

        # Delete status notification message
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")
    finally:
        # Cleanup
        for f in TEMP_DIR.glob(f"{task_id}_*"):
            try:
                f.unlink()
            except Exception:
                pass

def main():
    print("🚀 Starting VPS Telegram Bot Listener...")
    request = HTTPXRequest(read_timeout=120.0, write_timeout=120.0, connect_timeout=60.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
