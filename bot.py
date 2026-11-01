import os
import re
import glob
import asyncio
from pathlib import Path
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

BOT_TOKEN = os.getenv("BOT_TOKEN", "9280771787:AAGKrgffYGOEmHBxR4IF9RZPjj_8D8nyDcc")
ALLOWED_CHAT_ID = os.getenv("CHAT_ID", "-5155020880")

TEMP_DIR = Path("./temp_downloads")
TEMP_DIR.mkdir(exist_ok=True)

YOUTUBE_REGEX = r'(https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+)'

# Cobalt API public instances list (auto fallback)
COBALT_APIS = [
    "https://api.cobalt.tools",
    "https://cobalt-api.kwiatekm.tokyo",
    "https://cobalt.canine.tools",
    "https://cobalt.bowring.uk"
]

async def download_with_cobalt(url: str, output_path: Path):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    payload = {
        "url": url,
        "videoQuality": "720",
        "youtubeVideoCodec": "h264"
    }

    direct_url = None
    filename = "video.mp4"

    async with httpx.AsyncClient(timeout=45.0) as client:
        for api_base in COBALT_APIS:
            try:
                resp = await client.post(api_base, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status")
                    if status in ("stream", "redirect", "tunnel"):
                        direct_url = data.get("url")
                        filename = data.get("filename", filename)
                        break
                    elif status == "picker":
                        picker = data.get("picker", [])
                        if picker:
                            direct_url = picker[0].get("url")
                            break
            except Exception:
                continue

    if not direct_url:
        raise Exception("Could not fetch download stream from Cobalt API. All instances failed or rate limited.")

    # Download file chunks
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as dl_client:
        async with dl_client.stream("GET", direct_url) as stream:
            if stream.status_code >= 400:
                raise Exception(f"Download stream error HTTP {stream.status_code}")
            with open(output_path, "wb") as f:
                async for chunk in stream.aiter_bytes(chunk_size=1024 * 64):
                    f.write(chunk)

    return filename

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

    url = match.group(0)
    status_msg = await update.effective_message.reply_text("⚡ Link received! Fetching video via Cobalt API...")

    task_id = f"cobalt_{int(asyncio.get_event_loop().time() * 1000)}"
    video_file = TEMP_DIR / f"{task_id}.mp4"

    try:
        filename = await download_with_cobalt(url, video_file)
        
        if not video_file.exists():
            await status_msg.edit_text("❌ Download failed.")
            return

        size_mb = video_file.stat().st_size / (1024 * 1024)
        if size_mb > 50:
            await status_msg.edit_text(f"⚠️ Video size is {size_mb:.1f} MB (exceeds Telegram 50 MB limit).")
            return

        await status_msg.edit_text("📤 Uploading Video and Document to Telegram...")
        caption = f"🎥 *{filename}*\n🔗 [Original Link]({url})"

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
                caption=f"📁 *Document Archive*\n{filename}",
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
    print("🚀 Starting VPS Telegram Bot (Cobalt API Engine)...")
    request = HTTPXRequest(read_timeout=120.0, write_timeout=120.0, connect_timeout=60.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
