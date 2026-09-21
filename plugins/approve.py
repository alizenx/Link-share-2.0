from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot import Bot
from config import DEFAULT_LINK_EXPIRY_SECONDS
from database.database import get_setting, set_setting, get_channels, set_channel_approve
from helper_func import is_admin_filter


@Bot.on_message(filters.command("reqtime") & is_admin_filter)
async def cmd_reqtime(client: Bot, message: Message):
    args = message.text.split()
    current = await get_setting("link_expiry", DEFAULT_LINK_EXPIRY_SECONDS)
    if len(args) != 2 or not args[1].isdigit():
        await message.reply_text(f"Usage: <code>/reqtime seconds</code>\nCurrent: {current}s")
        return
    await set_setting("link_expiry", int(args[1]))
    await message.reply_text(f"✅ Join-request links now valid for {args[1]} second(s).")


@Bot.on_message(filters.command("reqmode") & is_admin_filter)
async def cmd_reqmode(client: Bot, message: Message):
    current = await get_setting("auto_approve", True)
    new_state = not current
    await set_setting("auto_approve", new_state)
    await message.reply_text(f"✅ Global auto-approve is now {'ON ✅' if new_state else 'OFF 🚫'}.")


async def _channel_picker(action: str):
    channels = await get_channels(None)
    if not channels:
        return None
    rows = [[InlineKeyboardButton(c.get("title", str(c["_id"]))[:40], callback_data=f"{action}:{c['_id']}")] for c in channels]
    return InlineKeyboardMarkup(rows)


@Bot.on_message(filters.command("approveon") & is_admin_filter)
async def cmd_approveon(client: Bot, message: Message):
    kb = await _channel_picker("apprvon")
    if kb is None:
        await message.reply_text("No channels registered yet.")
        return
    await message.reply_text("✅ Pick a channel to enable auto-approve:", reply_markup=kb)


@Bot.on_message(filters.command("approveoff") & is_admin_filter)
async def cmd_approveoff(client: Bot, message: Message):
    kb = await _channel_picker("apprvoff")
    if kb is None:
        await message.reply_text("No channels registered yet.")
        return
    await message.reply_text("🚫 Pick a channel to disable auto-approve:", reply_markup=kb)


@Bot.on_callback_query(filters.regex(r"^apprvon:"))
async def cb_apprvon(client: Bot, call: CallbackQuery):
    channel_id = int(call.data.split(":", 1)[1])
    await set_channel_approve(channel_id, True)
    await call.answer("Auto-approve enabled.")
    await call.message.edit_text("✅ Auto-approve enabled for this channel.")


@Bot.on_callback_query(filters.regex(r"^apprvoff:"))
async def cb_apprvoff(client: Bot, call: CallbackQuery):
    channel_id = int(call.data.split(":", 1)[1])
    await set_channel_approve(channel_id, False)
    await call.answer("Auto-approve disabled.")
    await call.message.edit_text("🚫 Auto-approve disabled for this channel. Requests need manual approval in Telegram.")
