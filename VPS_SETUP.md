# YouTube to Telegram Archiver (VPS Deployment)

## 1. On your VPS (Ubuntu/Debian):

```bash
# Update and install python & ffmpeg
sudo apt update && sudo apt install -y python3 python3-pip python3-venv ffmpeg git

# Clone your repository
git clone <YOUR_GITHUB_REPO_URL>
cd <REPO_FOLDER>/local-archiver

# Setup venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Run it 24/7 in the Background using Systemd

Create a systemd service file:
```bash
sudo nano /etc/systemd/system/telegram-archiver.service
```

Paste this content (replace `/root/local-archiver` with your actual path):
```ini
[Unit]
Description=YouTube to Telegram Archiver Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/local-archiver
ExecStart=/root/local-archiver/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 3. Enable and Start the Bot:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-archiver
sudo systemctl start telegram-archiver
```

To check logs:
```bash
sudo systemctl status telegram-archiver
journalctl -u telegram-archiver -f
```

Now, any time you paste a YouTube link in your **`sodo-player`** group, your VPS will automatically download and send both the **video** and **document** formats into the group!
