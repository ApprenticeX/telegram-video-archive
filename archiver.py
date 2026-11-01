import os
import sys
import glob
import asyncio
from pathlib import Path
from typing import Optional
import yt_dlp
from telegram import Bot
from telegram.request import HTTPXRequest

# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9280771787:AAGKrgffYGOEmHBxR4IF9RZPjj_8D8nyDcc")
CHAT_ID = os.environ.get("CHAT_ID", "-5155020880")  # sodo-player group

TEMP_DIR = Path("./temp_downloads")
TEMP_DIR.mkdir(exist_ok=True)

def get_cookies_file() -> Optional[str]:
    env_path = os.getenv("COOKIES_PATH") or os.getenv("YOUTUBE_COOKIES_PATH")
    if env_path and Path(env_path).is_file():
        return str(Path(env_path).resolve())

    for candidate in [Path("cookies.txt"), TEMP_DIR / "cookies.txt"]:
        if candidate.is_file():
            return str(candidate.resolve())

    raw_cookies = os.getenv("YOUTUBE_COOKIES")
    if raw_cookies and raw_cookies.strip():
        try:
            content = raw_cookies.strip()
            if not content.startswith("#") and " " not in content and len(content) > 50:
                try:
                    import base64
                    decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
                    if "youtube.com" in decoded or "# Netscape" in decoded:
                        content = decoded
                except Exception:
                    pass

            target = TEMP_DIR / "cookies.txt"
            target.write_text(content, encoding="utf-8")
            return str(target.resolve())
        except Exception:
            pass

    return None

async def archive_video(url: str, custom_chat_id: str = None):
    target_chat = custom_chat_id or CHAT_ID
    print(f"\n==========================================")
    print(f"📥 Processing URL: {url}")
    print(f"🎯 Target Telegram Chat: {target_chat}")
    print(f"==========================================")

    # 1. Download Video with yt-dlp
    out_tmpl = str(TEMP_DIR / "%(id)s_%(title).80s.%(ext)s")
    base_ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': out_tmpl,
        'writethumbnail': True,
        'quiet': False,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'mweb', 'web'],
            }
        }
    }

    cookies_file = get_cookies_file()
    if cookies_file:
        base_ydl_opts['cookiefile'] = cookies_file
        print(f"🍪 Using cookies: {cookies_file}")

    loop = asyncio.get_event_loop()
    def download():
        try:
            with yt_dlp.YoutubeDL(base_ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)
        except Exception as e:
            err_msg = str(e).lower()
            if "bot" in err_msg or "sign in" in err_msg or "requested format is not available" in err_msg:
                print("🔄 Bot detection encountered. Retrying with Android client...")
                fallback_opts = dict(base_ydl_opts)
                fallback_opts['format'] = '18/best[ext=mp4]/best'
                fallback_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': ['android'],
                    }
                }
                with yt_dlp.YoutubeDL(fallback_opts) as ydl_fb:
                    return ydl_fb.extract_info(url, download=True)
            raise e

    print("\n⏳ Downloading media using yt-dlp...")
    try:
        info = await loop.run_in_executor(None, download)
        video_id = info.get('id', 'video')
        title = info.get('title', 'YouTube Video')
        uploader = info.get('uploader', 'Unknown Channel')
    except Exception as e:
        print(f"❌ Failed to download video: {e}")
        return

    # Find the downloaded video & thumbnail
    video_file = None
    thumb_file = None
    for f in TEMP_DIR.glob(f"{video_id}_*"):
        if f.suffix.lower() in ('.mp4', '.mkv', '.webm'):
            video_file = f
        elif f.suffix.lower() in ('.jpg', '.jpeg', '.webp', '.png'):
            thumb_file = f

    if not video_file or not video_file.exists():
        print("❌ Could not find downloaded video file.")
        return

    file_size_mb = video_file.stat().st_size / (1024 * 1024)
    print(f"\n✅ Download complete! File size: {file_size_mb:.2f} MB")

    if file_size_mb > 50:
        print(f"⚠️ Warning: File size ({file_size_mb:.2f} MB) exceeds Telegram standard bot upload limit (50 MB).")
        print("   Skipping upload to prevent Telegram 413 error.")
        _cleanup(video_id)
        return

    # 2. Upload to Telegram
    request = HTTPXRequest(read_timeout=120.0, write_timeout=120.0, connect_timeout=60.0)
    bot = Bot(token=BOT_TOKEN, request=request)

    caption = f"🎥 *{title}*\n👤 {uploader}\n🔗 [Original Link]({url})"

    try:
        print("\n📤 1/2: Uploading as playable Video to Telegram...")
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
                print("   ✅ Video sent successfully!")
            finally:
                if thumb:
                    thumb.close()

        print("\n📤 2/2: Uploading as raw Document (uncompressed file) to Telegram...")
        with open(video_file, "rb") as df:
            await bot.send_document(
                chat_id=target_chat,
                document=df,
                caption=f"📁 *Document Archive*\n{title}",
                parse_mode="Markdown"
            )
            print("   ✅ Document sent successfully!")

        print("\n🎉 ALL DONE! Video & Document are both in your Telegram group.")

    except Exception as e:
        print(f"❌ Telegram upload error: {e}")
    finally:
        # 3. Clean up disk space
        print("\n🧹 Cleaning up temporary files on disk...")
        _cleanup(video_id)
        print("✨ Local disk cleaned.")

def _cleanup(video_id: str):
    for f in TEMP_DIR.glob(f"{video_id}_*"):
        try:
            f.unlink()
        except Exception:
            pass

def main():
    if len(sys.argv) > 1:
        url = sys.argv[1].strip()
    else:
        print("==========================================")
        print("📺 YouTube to Telegram Archiver (Local)")
        print("==========================================")
        url = input("👉 Paste YouTube URL: ").strip()

    if not url:
        print("No URL provided. Exiting.")
        return

    asyncio.run(archive_video(url))

if __name__ == "__main__":
    main()
