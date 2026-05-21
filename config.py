"""
Edit this file with your credentials and channel list before running.
"""

# --- Telegram API credentials ---
# Get these from https://my.telegram.org → "API development tools"
API_ID = 0           # replace with your integer api_id
API_HASH = ""        # replace with your api_hash string

# Session file name (stored locally, keeps you logged in)
SESSION_NAME = "tg_downloader"

# --- Channels to watch / bulk-download ---
# Use @username, invite links, or numeric channel IDs
CHANNELS = [
    "@example_channel",
    # "https://t.me/another_channel",
    # -1001234567890,
]

# --- Download settings ---
DOWNLOAD_DIR = "downloads"      # folder where videos are saved
MAX_FILE_SIZE_MB = 0            # 0 = no limit; e.g. 500 to skip files > 500 MB

# --- Status web server ---
STATUS_PORT = 3005              # visit http://your-server-ip:3005 to see live status

# --- Forward to Telegram ---
# "me" = your Saved Messages. Or use a chat ID / @username to forward elsewhere.
FORWARD_TO = "me"
