"""
Telegram Video Downloader
- Auto-monitors channels for new videos
- Bulk-downloads past videos from channel history
- Saves to downloads/<channel_name>/
"""

import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
from telethon.tl.functions.channels import GetFullChannelRequest

from config import API_ID, API_HASH, SESSION_NAME, CHANNELS, DOWNLOAD_DIR, MAX_FILE_SIZE_MB


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


async def download_message(client: TelegramClient, message, channel_name: str):
    if not is_video(message):
        return

    size_mb = get_file_size_mb(message)
    if MAX_FILE_SIZE_MB > 0 and size_mb > MAX_FILE_SIZE_MB:
        print(f"  [skip] msg {message.id} — {size_mb:.1f} MB exceeds limit ({MAX_FILE_SIZE_MB} MB)")
        return

    filename = make_filename(message, channel_name)
    save_path = get_save_path(channel_name, filename)

    if save_path.exists():
        print(f"  [exists] {save_path.name}")
        return

    size_str = f"{size_mb:.1f} MB" if size_mb else "? MB"
    print(f"  [download] {save_path.name} ({size_str})")

    def progress(current, total):
        pct = current / total * 100 if total else 0
        print(f"\r    {pct:.1f}%  {current/(1024*1024):.1f}/{total/(1024*1024):.1f} MB", end="", flush=True)

    await client.download_media(message, file=str(save_path), progress_callback=progress)
    print(f"\r    done.{' ' * 30}")


async def bulk_download(client: TelegramClient, channel: str):
    print(f"\n[bulk] Fetching history from: {channel}")
    entity = await client.get_entity(channel)
    channel_name = getattr(entity, "title", channel)
    count = 0
    async for message in client.iter_messages(entity, reverse=True):
        if is_video(message):
            count += 1
            print(f"  [{count}] {message.date.strftime('%Y-%m-%d')} msg_id={message.id}")
            await download_message(client, message, channel_name)
    print(f"[bulk] Done. {count} video(s) found in {channel_name}.")


async def monitor(client: TelegramClient):
    print(f"\n[monitor] Watching channels: {', '.join(CHANNELS)}")
    print("[monitor] Press Ctrl+C to stop.\n")

    entities = {}
    for ch in CHANNELS:
        try:
            e = await client.get_entity(ch)
            entities[e.id] = (e, getattr(e, "title", ch))
        except Exception as ex:
            print(f"  [warn] Could not resolve '{ch}': {ex}")

    @client.on(events.NewMessage(chats=list(entities.keys())))
    async def handler(event):
        entity_id = event.chat_id
        _, channel_name = entities.get(entity_id, (None, str(entity_id)))
        if is_video(event.message):
            print(f"\n[new video] {channel_name} — msg {event.message.id}")
            await download_message(client, event.message, channel_name)

    await client.run_until_disconnected()


async def main():
    mode = "both"
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()  # "monitor", "bulk", or "both"

    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        print(f"Logged in as: {(await client.get_me()).first_name}")

        if mode in ("bulk", "both"):
            for ch in CHANNELS:
                await bulk_download(client, ch)

        if mode in ("monitor", "both"):
            await monitor(client)


if __name__ == "__main__":
    asyncio.run(main())
