from datetime import datetime, timedelta

from pyrogram import filters
from pyrogram.types import (
    Message, CallbackQuery, ChatJoinRequest,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from bot import Bot
from config import OWNER_ID, DEFAULT_LINK_EXPIRY_SECONDS, EXTRA_BUTTON_LABEL, EXTRA_BUTTON_URL, WELCOME_TEXT, ABOUT_TEXT, LOGGER
from database.database import (
    add_user, get_post, get_channel, get_setting,
    save_request, get_request, delete_request,
)
from helper_func import esc, is_admin_filter

logger = LOGGER(__name__)


def channel_post_link(channel_id: int, message_id: int) -> str:
    internal_id = str(channel_id).replace("-100", "", 1)
    return f"https://t.me/c/{internal_id}/{message_id}"


async def link_expiry_seconds() -> int:
    return await get_setting("link_expiry", DEFAULT_LINK_EXPIRY_SECONDS)


async def auto_approve_enabled() -> bool:
    return await get_setting("auto_approve", True)


def welcome_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("• ABOUT •", callback_data="about"),
            InlineKeyboardButton("• CHANNELS •", callback_data="idx:menu:all"),
        ],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🗂 ADMIN PANEL", callback_data="apanel:home")])
    return InlineKeyboardMarkup(rows)


async def send_join_request_prompt(client: Bot, chat_id: int, user_id: int, first_name: str,
                                    post_code: str, channel_id: int, edit_message_id: int = None):
    try:
        # Pyrogram wants a datetime here, not a Unix timestamp int (that was
        # the telebot-style API the source bots copied expire_date from).
        expire_dt = datetime.now() + timedelta(seconds=await link_expiry_seconds())
        invite = await client.create_chat_invite_link(
            chat_id=channel_id,
            name=f"req-{post_code}-{user_id}"[:32],
            expire_date=expire_dt,
            creates_join_request=True,
        )
    except Exception as e:
        text = (
            "❌ Could not create an invite link. Make sure the bot is an admin "
            f"in that channel with the \"Invite Users via Link\" permission.\n\n<code>{esc(e)}</code>"
        )
        if edit_message_id:
            try:
                await client.edit_message_text(chat_id, edit_message_id, text)
                return
            except Exception:
                pass
        await client.send_message(chat_id, text)
        return

    await save_request(invite.invite_link, post_code, channel_id, user_id)

    greeting = f"Hey {esc(first_name)},\n\n" if first_name else ""
    text = (
        greeting + "<blockquote>Here is your link! Click below to proceed.</blockquote>\n\n"
        "<i>If the link has expired, tap the post link again to get a new one.</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("• REQUEST TO JOIN •", url=invite.invite_link)]])
    if edit_message_id:
        try:
            await client.edit_message_text(chat_id, edit_message_id, text, reply_markup=kb)
            return
        except Exception:
            pass
    await client.send_message(chat_id, text, reply_markup=kb)


@Bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Bot, message: Message):
    user_id = message.from_user.id
    await add_user(user_id)

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        is_admin = await is_admin_filter(client, message)
        await message.reply_text(WELCOME_TEXT, reply_markup=welcome_keyboard(is_admin), disable_web_page_preview=True)
        return

    post_code = args[1].strip()
    post = await get_post(post_code)
    if not post:
        await message.reply_text("❌ This link is invalid or has been removed.")
        return

    await send_join_request_prompt(
        client, message.chat.id, user_id, message.from_user.first_name,
        post_code, post["channel_id"],
    )


@Bot.on_callback_query(filters.regex(r"^getlink:"))
async def cb_getlink(client: Bot, call: CallbackQuery):
    post_code = call.data.split(":", 1)[1]
    post = await get_post(post_code)
    if not post:
        await call.answer("❌ This link is invalid or has been removed.", show_alert=True)
        return
    await call.answer()
    await send_join_request_prompt(
        client, call.message.chat.id, call.from_user.id, call.from_user.first_name,
        post_code, post["channel_id"], edit_message_id=call.message.id,
    )


@Bot.on_callback_query(filters.regex(r"^about$"))
async def cb_about(client: Bot, call: CallbackQuery):
    await call.answer()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="backhome")]])
    try:
        await call.message.edit_text(ABOUT_TEXT, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        pass


@Bot.on_callback_query(filters.regex(r"^backhome$"))
async def cb_backhome(client: Bot, call: CallbackQuery):
    await call.answer()
    is_admin = await is_admin_filter(client, call)
    try:
        await call.message.edit_text(WELCOME_TEXT, reply_markup=welcome_keyboard(is_admin), disable_web_page_preview=True)
    except Exception:
        pass


# =========================================================================
# Join-request handling. Only requests created THROUGH this bot (i.e. that
# went through save_request above) are tracked and auto-approved -- a
# manual/native join request on a registered channel is left untouched for
# a human admin to handle in Telegram itself.
# =========================================================================
@Bot.on_chat_join_request()
async def handle_join_request(client: Bot, request: ChatJoinRequest):
    used_link = request.invite_link.invite_link if request.invite_link else None
    if not used_link:
        return

    entry = await get_request(used_link)
    if not entry:
        return  # unrelated/manual request -- leave for native approval

    channel_id = entry["channel_id"]
    channel = await get_channel(channel_id) or {}
    expiry = await link_expiry_seconds()
    created_at = entry["created_at"]
    if isinstance(created_at, datetime) and (datetime.utcnow() - created_at) > timedelta(seconds=expiry):
        try:
            await client.decline_chat_join_request(channel_id, request.from_user.id)
        except Exception:
            pass
        try:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Get New Link", callback_data=f"getlink:{entry['post_code']}")]])
            await client.send_message(request.from_user.id, "❌ That link has expired. Tap below for a fresh one.", reply_markup=kb)
        except Exception:
            pass
        await delete_request(used_link)
        return

    channel_allows = channel.get("approve", True)
    if not await auto_approve_enabled() or not channel_allows:
        try:
            await client.send_message(request.from_user.id, "⏳ Your join request needs manual approval by an admin. Please wait.")
        except Exception:
            pass
        return

    try:
        await client.approve_chat_join_request(channel_id, request.from_user.id)
    except Exception as e:
        logger.error(f"Approve failed for {request.from_user.id} in {channel_id}: {e}")
        return

    post = await get_post(entry["post_code"]) if entry.get("post_code") else None
    post_link = channel_post_link(channel_id, post["message_id"]) if post and post.get("message_id") else None
    channel_title = channel.get("title", "the channel")

    caption = (
        f"Hey {esc(request.from_user.first_name or '')},\n\n"
        f"<blockquote>Your request to join <b>{esc(channel_title)}</b> has been approved.</blockquote>"
    )
    rows = []
    if post_link:
        rows.append([InlineKeyboardButton("🔗 Open Post", url=post_link)])
    if EXTRA_BUTTON_URL:
        rows.append([InlineKeyboardButton(EXTRA_BUTTON_LABEL, url=EXTRA_BUTTON_URL)])
    rows.append([InlineKeyboardButton(f"• JOIN {channel_title[:30]} •", url=used_link)])

    try:
        await client.send_message(request.from_user.id, caption, reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e:
        logger.info(f"Could not DM approved user {request.from_user.id} (likely blocked the bot): {e}")

    await delete_request(used_link)
