import asyncio

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from bot import Bot
from config import LOGGER
from database.database import full_userbase, get_channels
from helper_func import is_admin_filter

logger = LOGGER(__name__)


async def _delete_after(client: Bot, chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception:
        pass


async def _broadcast_to(client: Bot, reply_to: Message, target_ids, delay: int = None):
    sent, failed = 0, 0
    for target_id in target_ids:
        try:
            sent_msg = await reply_to.copy(target_id)
            if delay:
                asyncio.create_task(_delete_after(client, target_id, sent_msg.id, delay))
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                sent_msg = await reply_to.copy(target_id)
                if delay:
                    asyncio.create_task(_delete_after(client, target_id, sent_msg.id, delay))
                sent += 1
            except Exception:
                failed += 1
        except Exception as e:
            logger.info(f"Broadcast to {target_id} failed: {e}")
            failed += 1
        await asyncio.sleep(0.05)  # gentle pacing to avoid hard flood limits
    return sent, failed


def _parse_timed(message: Message, command_name: str):
    """Returns (delay_or_None, error_or_None). command_name e.g. 'tbroadcast'."""
    parts = message.text.split()
    is_timed = parts[0].lstrip("/").lower().startswith("t")
    if not is_timed:
        return None, None
    if len(parts) < 2 or not parts[1].isdigit():
        return None, f"Usage: /{command_name} seconds (as a reply to the message to send)"
    return int(parts[1]), None


@Bot.on_message(filters.command(["broadcast", "tbroadcast"]) & filters.private & is_admin_filter)
async def cmd_broadcast(client: Bot, message: Message):
    if not message.reply_to_message:
        await message.reply_text("❌ Reply to the message you want to broadcast with this command.")
        return
    delay, error = _parse_timed(message, "tbroadcast")
    if error:
        await message.reply_text(error)
        return
    user_ids = await full_userbase()
    status = await message.reply_text(f"📢 Broadcasting to {len(user_ids)} user(s)...")
    sent, failed = await _broadcast_to(client, message.reply_to_message, user_ids, delay)
    await status.edit_text(f"✅ Broadcast done. Sent: {sent}, Failed: {failed}.")


@Bot.on_message(filters.command(["cbalanced", "tcbalanced"]) & filters.private & is_admin_filter)
async def cmd_cbalanced(client: Bot, message: Message):
    if not message.reply_to_message:
        await message.reply_text("❌ Reply to the message you want to broadcast with this command.")
        return
    delay, error = _parse_timed(message, "tcbalanced")
    if error:
        await message.reply_text(error)
        return
    channels = await get_channels(None)
    channel_ids = [c["_id"] for c in channels]
    status = await message.reply_text(f"📢 Sending to {len(channel_ids)} channel(s)...")
    sent, failed = await _broadcast_to(client, message.reply_to_message, channel_ids, delay)
    await status.edit_text(f"✅ Sent to channels. Sent: {sent}, Failed: {failed}.")
