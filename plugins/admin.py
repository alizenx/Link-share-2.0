from pyrogram import filters
from pyrogram.types import Message, ChatPrivileges

from bot import Bot
from config import OWNER_ID
from database.database import add_admin, remove_admin, list_admins, get_channels
from helper_func import esc, is_owner_filter

# NOTE: granting a real Telegram channel-admin role is powerful (it can be
# used to take over a channel), so /addadmin, /deladmin, /adminme and
# /adminmeall are OWNER-only here -- neither source bot enforced this
# consistently, which let a bot-level admin escalate to real channel admin
# rights.
#
# Modern Pyrogram/Pyrofork takes a ChatPrivileges object for
# promote_chat_member, not individual can_* booleans (that was the older
# telebot-style API the source bots copied from) -- passing booleans as
# kwargs here would raise a TypeError at call time.
CHANNEL_ADMIN_PRIVILEGES = ChatPrivileges(
    can_change_info=True, can_post_messages=True, can_edit_messages=True,
    can_delete_messages=True, can_invite_users=True, can_restrict_members=True,
    can_pin_messages=True, can_promote_members=True, can_manage_chat=True,
    can_manage_video_chats=True,
)


@Bot.on_message(filters.command("addadmin") & is_owner_filter)
async def cmd_addadmin(client: Bot, message: Message):
    args = message.text.split()
    if len(args) != 2 or not args[1].lstrip("-").isdigit():
        await message.reply_text("Usage: <code>/addadmin user_id</code>")
        return
    user_id = int(args[1])
    await add_admin(user_id)
    await message.reply_text(f"✅ <code>{user_id}</code> is now a bot admin.")


@Bot.on_message(filters.command("deladmin") & is_owner_filter)
async def cmd_deladmin(client: Bot, message: Message):
    args = message.text.split()
    if len(args) != 2 or not args[1].lstrip("-").isdigit():
        await message.reply_text("Usage: <code>/deladmin user_id</code>")
        return
    user_id = int(args[1])
    if user_id == OWNER_ID:
        await message.reply_text("❌ Can't remove the owner.")
        return
    if await remove_admin(user_id):
        await message.reply_text(f"✅ <code>{user_id}</code> removed from bot admins.")
    else:
        await message.reply_text("❌ That user wasn't a bot admin.")


@Bot.on_message(filters.command("admins") & is_owner_filter)
async def cmd_admins(client: Bot, message: Message):
    admins = await list_admins()
    admins = sorted(set(admins) | {OWNER_ID})
    text = "<b>Bot Admins:</b>\n" + "\n".join(f"<code>{a}</code>{' (owner)' if a == OWNER_ID else ''}" for a in admins)
    await message.reply_text(text)


@Bot.on_message(filters.command("adminme") & is_owner_filter)
async def cmd_adminme(client: Bot, message: Message):
    args = message.text.split()
    if len(args) < 3 or not args[1].lstrip("-").isdigit() or not args[2].lstrip("-").isdigit():
        await message.reply_text("Usage: <code>/adminme user_id channel_id</code>")
        return
    target_id, channel_id = int(args[1]), int(args[2])
    try:
        await client.promote_chat_member(channel_id, target_id, privileges=CHANNEL_ADMIN_PRIVILEGES)
    except Exception as e:
        await message.reply_text(f"❌ Failed: {esc(e)}")
        return
    await message.reply_text(f"✅ <code>{target_id}</code> is now a channel admin in <code>{channel_id}</code>.")


@Bot.on_message(filters.command("adminmeall") & is_owner_filter)
async def cmd_adminmeall(client: Bot, message: Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].lstrip("-").isdigit():
        await message.reply_text("Usage: <code>/adminmeall user_id</code>")
        return
    target_id = int(args[1])
    channels = await get_channels(None)
    if not channels:
        await message.reply_text("No channels registered yet.")
        return
    done, failed = 0, 0
    for c in channels:
        try:
            await client.promote_chat_member(c["_id"], target_id, privileges=CHANNEL_ADMIN_PRIVILEGES)
            done += 1
        except Exception:
            failed += 1
    await message.reply_text(f"✅ Promoted in {done} channel(s). Failed: {failed}.")
