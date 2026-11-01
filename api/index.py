import os
import glob
import asyncio
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
from telegram import Bot
from telegram.request import HTTPXRequest

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9280771787:AAGKrgffYGOEmHBxR4IF9RZPjj_8D8nyDcc")
DEFAULT_CHAT_ID = os.environ.get("CHAT_ID", "-5155020880")

# On Vercel serverless, /tmp is writable; otherwise use local temp_downloads
TEMP_DIR = Path("/tmp") if os.path.exists("/tmp") else Path("./temp_downloads")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Telegram Media Archiver")

# In-memory status dictionary (for polling)
tasks_status = {}

class ArchiveReq(BaseModel):
    url: str
    chat_id: str | None = None

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YouTube to Telegram Archiver</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4">
  <div class="max-w-lg w-full bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl">
    <div class="flex items-center space-x-3 mb-6">
      <div class="w-11 h-11 rounded-2xl bg-indigo-600 flex items-center justify-center font-bold text-xl shadow-lg shadow-indigo-500/30">
        ⚡
      </div>
      <div>
        <h1 class="text-xl font-bold text-white tracking-wide">Telegram Media Archiver</h1>
        <p class="text-xs text-slate-400">Deployed on Vercel Serverless</p>
      </div>
    </div>

    <div class="space-y-4">
      <div>
        <label class="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">YouTube / Media URL</label>
        <input id="url" type="text" placeholder="https://www.youtube.com/watch?v=..." autofocus
               class="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-xl focus:outline-none focus:border-indigo-500 text-sm text-slate-200 placeholder-slate-500">
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">Telegram Chat ID (Optional)</label>
        <input id="chat_id" type="text" placeholder="Leave empty for default group"
               class="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-xl focus:outline-none focus:border-indigo-500 text-sm text-slate-200 placeholder-slate-500">
      </div>

      <button onclick="startArchive()" id="submitBtn" 
              class="w-full py-3.5 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.99] font-medium rounded-xl shadow-lg shadow-indigo-600/30 transition duration-150 flex items-center justify-center space-x-2 text-sm">
        <span>Download & Upload to Telegram</span>
      </button>

      <div id="statusBox" class="hidden mt-4 p-4 bg-slate-800/80 border border-slate-700/60 rounded-xl text-xs space-y-1">
        <div class="flex items-center justify-between text-slate-400 font-medium">
          <span>Processing Status</span>
          <span id="spinner" class="animate-spin text-indigo-400">⚡</span>
        </div>
        <p id="statusText" class="text-indigo-300 font-mono text-xs pt-1 break-words">Queued...</p>
      </div>
    </div>
  </div>

  <script>
    async function startArchive() {
      const url = document.getElementById("url").value.trim();
      const chatId = document.getElementById("chat_id").value.trim();
      if (!url) return alert("Please enter a media / YouTube URL!");

      const btn = document.getElementById("submitBtn");
      const statusBox = document.getElementById("statusBox");
      const statusText = document.getElementById("statusText");
      const spinner = document.getElementById("spinner");

      btn.disabled = true;
      btn.classList.add("opacity-50", "cursor-not-allowed");
      statusBox.classList.remove("hidden");
      spinner.classList.remove("hidden");
      statusText.innerText = "Initiating archive task...";

      try {
        const res = await fetch("/archive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url, chat_id: chatId || null })
        });
        
        const data = await res.json();
        if (data.error) {
          throw new Error(data.error);
        }

        const interval = setInterval(async () => {
          try {
            const sRes = await fetch(`/status/${data.task_id}`);
            const sData = await sRes.json();
            statusText.innerText = sData.status;

            if (sData.status.startsWith("Completed") || sData.status.startsWith("Error") || sData.status.startsWith("Failed")) {
              clearInterval(interval);
              btn.disabled = false;
              btn.classList.remove("opacity-50", "cursor-not-allowed");
              spinner.classList.add("hidden");
              if (sData.status.startsWith("Completed")) {
                document.getElementById("url").value = "";
              }
            }
          } catch (e) {
            console.error(e);
          }
        }, 1500);

      } catch (err) {
        statusText.innerText = "Error: " + err.message;
        btn.disabled = false;
        btn.classList.remove("opacity-50", "cursor-not-allowed");
        spinner.classList.add("hidden");
      }
    }
  </script>
</body>
</html>
"""

async def process_media(task_id: str, url: str, target_chat: str):
    tasks_status[task_id] = "Downloading media with yt-dlp..."
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
        title = info.get('title', 'Archived Media')
        uploader = info.get('uploader', 'Unknown')

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

        tasks_status[task_id] = "Completed! Both Video and Document uploaded to Telegram."

    except Exception as e:
        tasks_status[task_id] = f"Error: {str(e)}"
    finally:
        for f in TEMP_DIR.glob(f"{task_id}_*"):
            try:
                f.unlink()
            except Exception:
                pass

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return HTMLResponse(content=HTML_PAGE)

@app.post("/archive")
async def archive_endpoint(payload: ArchiveReq, background_tasks: BackgroundTasks):
    target_chat = payload.chat_id.strip() if payload.chat_id and payload.chat_id.strip() else DEFAULT_CHAT_ID
    task_id = f"task_{int(asyncio.get_event_loop().time() * 1000)}"
    tasks_status[task_id] = "Task queued..."
    background_tasks.add_task(process_media, task_id, payload.url, target_chat)
    return {"task_id": task_id}

@app.get("/status/{task_id}")
async def status_endpoint(task_id: str):
    return {"status": tasks_status.get(task_id, "Unknown or expired task")}
