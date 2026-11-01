# Telegram Media Archiver (Vercel Serverless & Local)

FastAPI service designed to download media (via yt-dlp) and upload directly to Telegram channels/chats as both playable Video and uncompressed Document archive.

## Deploy to Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new)

### Environment Variables
Configure the following in your Vercel Project Settings:
- `BOT_TOKEN`: Your Telegram Bot token.
- `CHAT_ID`: Target Telegram Chat/Channel ID (e.g. `-100...` or group ID).

## Local Development

```bash
pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000
```

Open `http://localhost:8000` in your browser.
