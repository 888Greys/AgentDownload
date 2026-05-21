# Telegram Video Downloader

Downloads videos from Telegram channels using your own account (no bot token needed).

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get Telegram API credentials
1. Go to https://my.telegram.org
2. Log in with your phone number
3. Click **"API development tools"**
4. Create an app — copy the `api_id` and `api_hash`

### 3. Edit config.py
```python
API_ID   = 12345678        # your integer api_id
API_HASH = "abcdef..."     # your api_hash
CHANNELS = ["@channel1", "@channel2"]
```

### 4. Run

**Bulk-download existing videos from channel history:**
```bash
python downloader.py bulk
```

**Monitor channels for new videos (runs until Ctrl+C):**
```bash
python downloader.py monitor
```

**Do both — bulk first, then keep watching:**
```bash
python downloader.py both
# or just:
python downloader.py
```

## First run
On first run Telethon will ask for your phone number and a login code (like signing into Telegram normally). This creates a `tg_downloader.session` file — keep it private, it's your login token.

## Downloads folder
Videos are saved to:
```
downloads/
  ChannelName/
    20260521_143000_video.mp4
    20260521_150012_msg99.mp4
```

## Notes
- `MAX_FILE_SIZE_MB` in config.py lets you skip very large files (set to `0` for no limit)
- The script skips files that already exist, so re-running is safe
- Works with public and private channels you're a member of
