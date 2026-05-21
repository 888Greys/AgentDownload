"""
Telegram Video Downloader
- Auto-monitors channels for new videos
- Bulk-downloads past videos from channel history
- Saves to downloads/<channel_name>/
- Status dashboard at http://server:3005
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from aiohttp import web

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument

from config import API_ID, API_HASH, SESSION_NAME, CHANNELS, DOWNLOAD_DIR, MAX_FILE_SIZE_MB, STATUS_PORT, FORWARD_TO


# --- Shared state for status dashboard ---
state = {
    "started": datetime.now().isoformat(),
    "mode": "starting",
    "channels": [],
    "active_download": None,
    "log": [],       # last 50 events
    "totals": {},    # channel -> count
}

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry)
    state["log"].append(entry)
    if len(state["log"]) > 50:
        state["log"].pop(0)


# --- Helpers ---

def sanitize(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def get_save_path(channel_name: str, filename: str) -> Path:
    folder = Path(DOWNLOAD_DIR) / sanitize(channel_name)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / filename


def is_video(message) -> bool:
    if not message.media:
        return False
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc.mime_type and doc.mime_type.startswith("video/"):
            return True
        for attr in doc.attributes:
            if attr.__class__.__name__ in ("DocumentAttributeVideo", "DocumentAttributeAnimated"):
                return True
    return False


def get_file_size_mb(message) -> float:
    try:
        return message.media.document.size / (1024 * 1024)
    except AttributeError:
        return 0


def make_filename(message, channel_name: str) -> str:
    date_str = message.date.strftime("%Y%m%d_%H%M%S")
    ext = ".mp4"
    try:
        for attr in message.media.document.attributes:
            if hasattr(attr, "file_name") and attr.file_name:
                return f"{date_str}_{sanitize(attr.file_name)}"
        mime = message.media.document.mime_type or ""
        if "webm" in mime:
            ext = ".webm"
        elif "mkv" in mime:
            ext = ".mkv"
        elif "mov" in mime:
            ext = ".mov"
    except AttributeError:
        pass
    return f"{date_str}_msg{message.id}{ext}"


# --- Downloader ---

async def download_message(client: TelegramClient, message, channel_name: str):
    if not is_video(message):
        return

    size_mb = get_file_size_mb(message)
    if MAX_FILE_SIZE_MB > 0 and size_mb > MAX_FILE_SIZE_MB:
        log(f"[skip] {channel_name} msg {message.id} — {size_mb:.1f} MB exceeds limit")
        return

    filename = make_filename(message, channel_name)
    save_path = get_save_path(channel_name, filename)

    if save_path.exists():
        log(f"[exists] {save_path.name}")
        return

    size_str = f"{size_mb:.1f} MB" if size_mb else "? MB"
    log(f"[download] {channel_name} / {save_path.name} ({size_str})")
    state["active_download"] = {"channel": channel_name, "file": save_path.name, "size": size_str}

    await client.download_media(message, file=str(save_path))

    state["active_download"] = None
    state["totals"][channel_name] = state["totals"].get(channel_name, 0) + 1
    log(f"[done] {save_path.name}")

    # Forward original message to Saved Messages (or configured destination)
    if FORWARD_TO:
        try:
            await client.forward_messages(FORWARD_TO, message)
            log(f"[forwarded] {save_path.name} → {FORWARD_TO}")
        except Exception as e:
            log(f"[forward error] {e}")


async def bulk_download(client: TelegramClient, channel, all_dialogs: list):
    log(f"[bulk] Starting history download: {channel}")
    entity = None
    # For numeric IDs, find the entity from already-loaded dialogs
    if isinstance(channel, int):
        target_id = abs(channel) % 10**10  # strip -100 prefix
        for d in all_dialogs:
            if getattr(d.entity, "id", None) == target_id:
                entity = d.entity
                break
    if entity is None:
        entity = await client.get_entity(channel)
    channel_name = getattr(entity, "title", str(channel))
    count = 0
    async for message in client.iter_messages(entity, reverse=True):
        if is_video(message):
            count += 1
            await download_message(client, message, channel_name)
    log(f"[bulk] Done — {count} video(s) from {channel_name}")


async def monitor(client: TelegramClient):
    state["mode"] = "monitoring"
    log(f"[monitor] Watching: {', '.join(CHANNELS)}")

    entities = {}
    for ch in CHANNELS:
        try:
            e = await client.get_entity(ch)
            entities[e.id] = (e, getattr(e, "title", ch))
        except Exception as ex:
            log(f"[warn] Could not resolve '{ch}': {ex}")

    state["channels"] = [name for _, name in entities.values()]

    @client.on(events.NewMessage(chats=list(entities.keys())))
    async def handler(event):
        _, channel_name = entities.get(event.chat_id, (None, str(event.chat_id)))
        if is_video(event.message):
            log(f"[new] {channel_name} — msg {event.message.id}")
            await download_message(client, event.message, channel_name)

    await client.run_until_disconnected()


# --- Status web server ---

async def handle_status(request):
    downloads = {}
    base = Path(DOWNLOAD_DIR)
    if base.exists():
        for ch_dir in base.iterdir():
            if ch_dir.is_dir():
                files = list(ch_dir.glob("*"))
                size_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
                downloads[ch_dir.name] = {"count": len(files), "size_mb": round(size_mb, 1)}

    html = f"""<!DOCTYPE html>
<html>
<head>
  <title>TG Downloader</title>
  <meta http-equiv="refresh" content="10">
  <style>
    body {{ font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 2rem; }}
    h1 {{ color: #58a6ff; }} h2 {{ color: #8b949e; border-bottom: 1px solid #21262d; padding-bottom: .3rem; }}
    .badge {{ background: #238636; color: #fff; padding: 2px 8px; border-radius: 10px; font-size: .8rem; }}
    .badge.idle {{ background: #6e7681; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
    td, th {{ padding: .4rem .8rem; border: 1px solid #21262d; text-align: left; }}
    th {{ background: #161b22; }}
    .log {{ background: #161b22; padding: 1rem; border-radius: 6px; font-size: .85rem; max-height: 300px; overflow-y: auto; }}
    .log div {{ margin-bottom: 2px; color: #8b949e; }}
    .log div:last-child {{ color: #c9d1d9; }}
  </style>
</head>
<body>
  <h1>Telegram Video Downloader</h1>
  <p>Mode: <span class="badge">{state["mode"]}</span> &nbsp;
     Started: {state["started"][:19].replace("T"," ")} &nbsp;
     Auto-refresh: 10s</p>

  <h2>Active Download</h2>
  {"<p><span class='badge'>" + state['active_download']['channel'] + "</span> " + state['active_download']['file'] + " (" + state['active_download']['size'] + ")</p>" if state['active_download'] else "<p><span class='badge idle'>idle</span></p>"}

  <h2>Downloads on Disk</h2>
  <table>
    <tr><th>Channel</th><th>Files</th><th>Total Size</th></tr>
    {"".join(f"<tr><td>{ch}</td><td>{info['count']}</td><td>{info['size_mb']} MB</td></tr>" for ch, info in downloads.items()) or "<tr><td colspan=3>No downloads yet</td></tr>"}
  </table>

  <h2>Recent Activity</h2>
  <div class="log">{"".join(f"<div>{e}</div>" for e in reversed(state["log"])) or "<div>No activity yet</div>"}</div>
</body>
</html>"""
    return web.Response(text=html, content_type="text/html")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_status)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", STATUS_PORT)
    await site.start()
    log(f"[web] Status dashboard: http://0.0.0.0:{STATUS_PORT}")


# --- Entry point ---

async def main():
    mode = "both"
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    state["mode"] = mode

    await start_web_server()

    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        me = await client.get_me()
        log(f"[auth] Logged in as: {me.first_name}")

        # Load ALL dialogs to populate entity cache
        log("[auth] Loading dialogs...")
        all_dialogs = await client.get_dialogs(limit=None)
        log(f"[auth] Loaded {len(all_dialogs)} dialogs")

        if mode in ("bulk", "both"):
            for ch in CHANNELS:
                await bulk_download(client, ch, all_dialogs)

        if mode in ("monitor", "both"):
            await monitor(client)


if __name__ == "__main__":
    asyncio.run(main())
