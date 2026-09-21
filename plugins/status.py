from datetime import datetime

from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot import Bot
from config import LOGGER
from database.database import (
    user_count, get_channels, get_setting, list_admins,
)
from helper_func import get_readable_time, is_admin_filter

logger = LOGGER(__name__)


async def status_text(client: Bot) -> str:
    uptime = get_readable_time(int((datetime.now() - client.uptime).total_seconds()))
    channels = await get_channels(None)
    admins = await list_admins()
    auto_approve = await get_setting("auto_approve", True)
    return (
        "📊 <b>Bot Status</b>\n\n"
        f"⏱ Uptime: {uptime}\n"
        f"👥 Known users: {await user_count()}\n"
        f"📢 Channels: {len(channels)}\n"
        f"🛡 Extra admins: {len(admins)}\n"
        f"⚙️ Auto-approve (global): {'ON ✅' if auto_approve else 'OFF 🚫'}"
    )


@Bot.on_message(filters.command("status") & is_admin_filter)
async def cmd_status(client: Bot, message: Message):
    await message.reply_text(await status_text(client))


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 All Channels", callback_data="chpage:None:1")],
        [InlineKeyboardButton("🎌 Anime", callback_data="chpage:anime:1"),
         InlineKeyboardButton("🎬 Drama", callback_data="chpage:drama:1")],
        [InlineKeyboardButton("✅ Approve ON", callback_data="apanel:approveon"),
         InlineKeyboardButton("🚫 Approve OFF", callback_data="apanel:approveoff")],
        [InlineKeyboardButton("📊 Status", callback_data="apanel:status")],
        [InlineKeyboardButton("🔙 Back", callback_data="backhome")],
    ])


@Bot.on_callback_query(filters.regex(r"^apanel:"))
async def cb_apanel(client: Bot, call: CallbackQuery):
    if not await is_admin_filter(client, call):
        await call.answer("❌ Admin only.", show_alert=True)
        return
    action = call.data.split(":", 1)[1]
    await call.answer()
    if action == "home":
        await call.message.edit_text("🗂 <b>Admin panel</b> — pick an action:", reply_markup=admin_panel_keyboard())
    elif action == "status":
        await call.message.edit_text(await status_text(client), reply_markup=admin_panel_keyboard())
    elif action in ("approveon", "approveoff"):
        from database.database import get_channels as _gc
        channels = await _gc(None)
        if not channels:
            await call.message.edit_text("No channels registered yet.", reply_markup=admin_panel_keyboard())
            return
        prefix = "apprvon" if action == "approveon" else "apprvoff"
        rows = [[InlineKeyboardButton(c.get("title", str(c["_id"]))[:40], callback_data=f"{prefix}:{c['_id']}")] for c in channels]
        rows.append([InlineKeyboardButton("🔙 Back", callback_data="apanel:home")])
        label = "enable" if action == "approveon" else "disable"
        await call.message.edit_text(f"Pick a channel to {label} auto-approve:", reply_markup=InlineKeyboardMarkup(rows))
