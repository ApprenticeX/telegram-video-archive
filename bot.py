import os
import re
import asyncio
from pathlib import Path
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

BOT_TOKEN = "9280771787:AAGKrgffYGOEmHBxR4IF9RZPjj_8D8nyDcc"
ALLOWED_CHAT_ID = "-5155020880"

TEMP_DIR = Path("./temp_downloads")
TEMP_DIR.mkdir(exist_ok=True)

YOUTUBE_REGEX = r'(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})'

# Multiple reliable open public Invidious instances
INVIDIOUS_INSTANCES = [
    "https://inv.tux.pizza",
    "https://vid.puffyan.us",
    "https://invidious.nerdvpn.de",
    "https://invidious.projectsegfau.lt",
    "https://invidious.drgns.space",
    "https://yt.drgnz.club"
]

async def download_video_stream(video_id: str, output_path: Path):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    title = "video"
    stream_url = None

    async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
        for instance in INVIDIOUS_INSTANCES:
            try:
                api_url = f"{instance}/api/v1/videos/{video_id}"
                resp = await client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", "YouTube Video")
                    formats = data.get("formatStreams", [])
                    # Pick best format (e.g. 720p or 360p with audio included)
                    if formats:
                        # Grab highest resolution stream
                        best_format = formats[-1]
                        stream_url = best_format.get("url")
                        if stream_url:
                            break
            except Exception:
                continue

    if not stream_url:
        raise Exception("Could not find video streams from Invidious instances.")

    # Download stream to file
    async with httpx.AsyncClient(timeout=180.0, headers=headers, follow_redirects=True) as dl_client:
        async with dl_client.stream("GET", stream_url) as response:
            if response.status_code >= 400:
                raise Exception(f"Failed to download stream: HTTP {response.status_code}")
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 64):
                    f.write(chunk)

    return title

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text:
        return

    text = update.effective_message.text
    chat_id = str(update.effective_chat.id)

    if ALLOWED_CHAT_ID and chat_id != str(ALLOWED_CHAT_ID):
        return

    match = re.search(YOUTUBE_REGEX, text)
    if not match:
        return

    video_id = match.group(1)
    url = f"https://www.youtube.com/watch?v={video_id}"
    status_msg = await update.effective_message.reply_text("⚡ Link received! Fetching video stream...")

    task_id = f"inv_{int(asyncio.get_event_loop().time() * 1000)}"
    video_file = TEMP_DIR / f"{task_id}.mp4"

    try:
        title = await download_video_stream(video_id, video_file)

        if not video_file.exists():
            await status_msg.edit_text("❌ Download failed.")
            return

        size_mb = video_file.stat().st_size / (1024 * 1024)
        if size_mb > 50:
            await status_msg.edit_text(f"⚠️ Video size is {size_mb:.1f} MB (exceeds Telegram 50 MB limit).")
            return

        await status_msg.edit_text("📤 Uploading Video and Document to Telegram...")
        caption = f"🎥 *{title}*\n🔗 [Original Link]({url})"

        # 1. Send as Video
        with open(video_file, "rb") as vf:
            await context.bot.send_video(
                chat_id=chat_id,
                video=vf,
                caption=caption,
                parse_mode="Markdown",
                supports_streaming=True
            )

        # 2. Send as Document
        with open(video_file, "rb") as df:
            await context.bot.send_document(
                chat_id=chat_id,
                document=df,
                caption=f"📁 *Document Archive*\n{title}",
                parse_mode="Markdown"
            )

        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")
    finally:
        if video_file.exists():
            try:
                video_file.unlink()
            except Exception:
                pass

def main():
    print("🚀 Starting VPS Telegram Bot (Invidious Direct Streams)...")
    request = HTTPXRequest(read_timeout=120.0, write_timeout=120.0, connect_timeout=60.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
