import os
import glob
import asyncio
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
from telegram import Bot
from telegram.request import HTTPXRequest
import uvicorn

BOT_TOKEN = "9280771787:AAGKrgffYGOEmHBxR4IF9RZPjj_8D8nyDcc"
DEFAULT_CHAT_ID = "-5155020880"

TEMP_DIR = Path("./temp_downloads")
TEMP_DIR.mkdir(exist_ok=True)

app = FastAPI()
tasks_status = {}

class ArchiveReq(BaseModel):
    url: str
    chat_id: str | None = None

async def process_media(task_id: str, url: str, target_chat: str):
    tasks_status[task_id] = "Downloading media with yt-dlp & merging with local FFmpeg..."
    out_tmpl = str(TEMP_DIR / f"{task_id}_%(title).80s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': out_tmpl,
        'writethumbnail': True,
        'quiet': False,
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
            tasks_status[task_id] = "Failed: Could not find downloaded file."
            return

        size_mb = video_file.stat().st_size / (1024 * 1024)
        if size_mb > 50:
            tasks_status[task_id] = f"Error: Size is {size_mb:.1f} MB (exceeds Telegram 50 MB standard bot limit)."
            return

        request = HTTPXRequest(read_timeout=120.0, write_timeout=120.0, connect_timeout=60.0)
        bot = Bot(token=BOT_TOKEN, request=request)
        caption = f"🎥 *{title}*\n👤 {uploader}\n🔗 [Original Link]({url})"

        # Upload as Video
        tasks_status[task_id] = "Uploading streamable Video to Telegram..."
        with open(video_file, "rb") as vf:
            thumb = open(thumb_file, "rb") if thumb_file and thumb_file.exists() else None
            try:
                await bot.send_video(
                    chat_id=target_chat,
                    video=vf,
                    thumbnail=thumb,
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True
                )
            finally:
                if thumb:
                    thumb.close()

        # Upload as Document
        tasks_status[task_id] = "Uploading raw Document to Telegram..."
        with open(video_file, "rb") as df:
            await bot.send_document(
                chat_id=target_chat,
                document=df,
                caption=f"📁 *Document Archive*\n{title}",
                parse_mode="Markdown"
            )

        tasks_status[task_id] = "Completed! Both Video and Document are in Telegram."

    except Exception as e:
        tasks_status[task_id] = f"Error: {str(e)}"
    finally:
        # Cleanup
        for f in TEMP_DIR.glob(f"{task_id}_*"):
            try:
                f.unlink()
            except Exception:
                pass

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("web_ui.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/archive")
async def archive_endpoint(payload: ArchiveReq, background_tasks: BackgroundTasks):
    target_chat = payload.chat_id.strip() if payload.chat_id and payload.chat_id.strip() else DEFAULT_CHAT_ID
    task_id = f"task_{int(asyncio.get_event_loop().time() * 1000)}"
    tasks_status[task_id] = "Task queued..."
    background_tasks.add_task(process_media, task_id, payload.url, target_chat)
    return {"task_id": task_id}

@app.get("/status/{task_id}")
async def status_endpoint(task_id: str):
    return {"status": tasks_status.get(task_id, "Unknown task")}

if __name__ == "__main__":
    print("=" * 55)
    print("🚀 Local Telegram Archiver Web UI running at:")
    print("👉 http://localhost:8000")
    print("=" * 55)
    uvicorn.run(app, host="127.0.0.1", port=8000)
