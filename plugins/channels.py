import math
from datetime import datetime, timedelta

from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot import Bot
from config import DEFAULT_LINK_EXPIRY_SECONDS
from database.database import (
    save_channel, get_channel, get_channels, delete_channel,
    set_channel_category, move_uncategorized, set_channel_approve,
    save_post, get_post, delete_post, get_posts_for_channel,
)
from helper_func import generate_code, esc, is_admin_filter

PER_PAGE = 10
CATEGORY_LABEL = {"anime": "🎌 Anime", "drama": "🎬 Drama", "all": "📋 All", None: "📋 All"}


def channel_link_fallback(channel_id: int) -> str:
    internal_id = str(channel_id).replace("-100", "", 1)
    return f"https://t.me/c/{internal_id}"


async def _register_channel(client: Bot, chat, category: str = None, forwarded_msg_id: int = None) -> str:
    existing = await get_channel(chat.id)
    join_code = existing["join_code"] if (existing and existing.get("join_code")) else ("J" + generate_code(5))

    invite_link = existing.get("invite_link") if existing else None
    if not invite_link:
        try:
            invite = await client.create_chat_invite_link(chat_id=chat.id, name="permanent")
            invite_link = invite.invite_link
        except Exception:
            invite_link = None  # bot may lack "Invite Users via Link" permission

    await save_channel(chat.id, chat.title or str(chat.id), category=category, join_code=join_code, invite_link=invite_link)
    # The channel's own permanent join code is itself a "post" with no
    # specific message -- this lets /start <join_code> and a real post code
    # share one lookup path (see plugins/start.py).
    await save_post(join_code, chat.id, None)

    bot_username = client.username
    permanent_link = f"https://t.me/{bot_username}?start={join_code}"
    category_label = category or "uncategorized -- use /setcategory to assign one"
    lines = [
        f"✅ Channel registered ({category_label}): <b>{esc(chat.title or chat.id)}</b>",
        f"\n🔗 Permanent join link (never expires):\n{permanent_link}",
    ]

    if forwarded_msg_id:
        post_code = "P" + generate_code(5)
        await save_post(post_code, chat.id, forwarded_msg_id)
        post_link = f"https://t.me/{bot_username}?start={post_code}"
        lines.append(f"\n📌 This specific post's link:\n{post_link}")

    return "\n".join(lines)


async def _forwarded_source(message: Message):
    """Returns the forward-origin chat + message id from a message the
    admin replied to, or (None, None) with an explanation."""
    replied = message.reply_to_message
    if replied is None or replied.forward_from_chat is None:
        return None, None, (
            "❌ First forward a post from the channel into this chat, then reply "
            "to that forwarded message with this command."
        )
    if not replied.forward_from_message_id:
        return None, None, "❌ Could not read the original message ID from that forward."
    return replied.forward_from_chat, replied.forward_from_message_id, None


@Bot.on_message(filters.command(["add", "addchannel"]) & is_admin_filter)
async def cmd_add(client: Bot, message: Message):
    chat, msg_id, error = await _forwarded_source(message)
    if error:
        await message.reply_text(error)
        return
    text = await _register_channel(client, chat, category=None, forwarded_msg_id=msg_id)
    await message.reply_text(text, disable_web_page_preview=True)


@Bot.on_message(filters.command("addanime") & is_admin_filter)
async def cmd_addanime(client: Bot, message: Message):
    chat, msg_id, error = await _forwarded_source(message)
    if error:
        await message.reply_text(error)
        return
    text = await _register_channel(client, chat, category="anime", forwarded_msg_id=msg_id)
    await message.reply_text(text, disable_web_page_preview=True)


@Bot.on_message(filters.command("adddrama") & is_admin_filter)
async def cmd_adddrama(client: Bot, message: Message):
    chat, msg_id, error = await _forwarded_source(message)
    if error:
        await message.reply_text(error)
        return
    text = await _register_channel(client, chat, category="drama", forwarded_msg_id=msg_id)
    await message.reply_text(text, disable_web_page_preview=True)


# ---------------- Pagination helpers ----------------
def _paginate(items, page, per_page=PER_PAGE):
    total_pages = max(1, math.ceil(len(items) / per_page))
    page = max(1, min(page, total_pages))
    return items[(page - 1) * per_page: page * per_page], page, total_pages


async def _channel_page(category, page):
    channels = sorted(await get_channels(category), key=lambda c: (c.get("title") or "").lower())
    label = CATEGORY_LABEL.get(category, category)
    if not channels:
        return f"No {label} channels registered yet.", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="apanel:home")]])

    page_items, page, total_pages = _paginate(channels, page)
    rows = [[InlineKeyboardButton(c.get("title", str(c["_id"]))[:40], callback_data=f"chpick:{c['_id']}:{category}:{page}")] for c in page_items]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"chpage:{category}:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"chpage:{category}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="apanel:home")])
    return f"{label} channels -- page {page}/{total_pages}:", InlineKeyboardMarkup(rows)


async def _channel_detail(client: Bot, channel_id, category, page):
    channel = await get_channel(channel_id)
    if not channel:
        return "❌ Channel not found (it may have been removed).", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"chpage:{category}:{page}")]])

    title = esc(channel.get("title", channel_id))
    join_link = f"https://t.me/{client.username}?start={channel.get('join_code', '')}" if channel.get("join_code") else "-"
    raw_link = channel.get("invite_link") or channel_link_fallback(channel_id)
    approve_state = "ON ✅" if channel.get("approve", True) else "OFF 🚫"
    posts = await get_posts_for_channel(channel_id)
    real_posts = [p for p in posts if p.get("message_id")]

    try:
        member_count = await client.get_chat_members_count(channel_id)
    except Exception:
        member_count = "unavailable"

    lines = [
        f"<b>{title}</b>",
        f"🔗 Bot join link: {esc(join_link)}",
        f"📢 Raw channel link: {esc(raw_link)}",
        f"👥 Members: {member_count}",
        f"⚙️ Auto-approve: {approve_state}",
        f"📌 Post links: {len(real_posts)}",
    ]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚙️ Auto-approve: {approve_state} (tap to toggle)", callback_data=f"chtoggle:{channel_id}:{category}:{page}")],
        [InlineKeyboardButton("🗑 Remove Channel", callback_data=f"chdel:{channel_id}:{category}:{page}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"chpage:{category}:{page}")],
    ])
    return "\n".join(lines), kb


@Bot.on_message(filters.command("channels") & is_admin_filter)
async def cmd_channels(client: Bot, message: Message):
    text, kb = await _channel_page(None, 1)
    await message.reply_text(text, reply_markup=kb)


@Bot.on_message(filters.command("animechannel") & is_admin_filter)
async def cmd_animechannel(client: Bot, message: Message):
    text, kb = await _channel_page("anime", 1)
    await message.reply_text(text, reply_markup=kb)


@Bot.on_message(filters.command("dramachannel") & is_admin_filter)
async def cmd_dramachannel(client: Bot, message: Message):
    text, kb = await _channel_page("drama", 1)
    await message.reply_text(text, reply_markup=kb)


@Bot.on_callback_query(filters.regex(r"^chpage:"))
async def cb_chpage(client: Bot, call: CallbackQuery):
    _, category, page = call.data.split(":")
    category = None if category == "None" else category
    text, kb = await _channel_page(category, int(page))
    await call.answer()
    await call.message.edit_text(text, reply_markup=kb)


@Bot.on_callback_query(filters.regex(r"^chpick:"))
async def cb_chpick(client: Bot, call: CallbackQuery):
    _, channel_id, category, page = call.data.split(":")
    text, kb = await _channel_detail(client, int(channel_id), category, int(page))
    await call.answer()
    await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)


@Bot.on_callback_query(filters.regex(r"^chtoggle:"))
async def cb_chtoggle(client: Bot, call: CallbackQuery):
    _, channel_id, category, page = call.data.split(":")
    channel_id = int(channel_id)
    channel = await get_channel(channel_id) or {}
    new_state = not channel.get("approve", True)
    await set_channel_approve(channel_id, new_state)
    await call.answer(f"Auto-approve {'ON' if new_state else 'OFF'}.")
    text, kb = await _channel_detail(client, channel_id, category, int(page))
    await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)


@Bot.on_callback_query(filters.regex(r"^chdel:"))
async def cb_chdel(client: Bot, call: CallbackQuery):
    _, channel_id, category, page = call.data.split(":")
    channel_id = int(channel_id)
    channel = await get_channel(channel_id) or {}
    title = channel.get("title", str(channel_id))
    await delete_channel(channel_id)
    await call.answer("Removed.")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"chpage:{category}:{page}")]])
    await call.message.edit_text(f"✅ Channel removed: {esc(title)}\n(Its post links were removed too.)", reply_markup=kb)


# ---------------- /del (removechannel) -- quick picker ----------------
@Bot.on_message(filters.command(["del", "removechannel"]) & is_admin_filter)
async def cmd_del(client: Bot, message: Message):
    channels = await get_channels(None)
    if not channels:
        await message.reply_text("No channels registered yet.")
        return
    rows = [[InlineKeyboardButton(f"🗑 {c.get('title', str(c['_id']))[:40]}", callback_data=f"chdel:{c['_id']}:None:1")] for c in channels]
    await message.reply_text("Pick a channel to remove:", reply_markup=InlineKeyboardMarkup(rows))


# ---------------- /setcategory ----------------
@Bot.on_message(filters.command("setcategory") & is_admin_filter)
async def cmd_setcategory(client: Bot, message: Message):
    channels = await get_channels(None)
    if not channels:
        await message.reply_text("No channels registered yet.")
        return
    rows = [[InlineKeyboardButton(c.get("title", str(c["_id"]))[:40], callback_data=f"setcat:{c['_id']}")] for c in channels]
    await message.reply_text("Pick a channel to set its category:", reply_markup=InlineKeyboardMarkup(rows))


@Bot.on_callback_query(filters.regex(r"^setcat:\d+$") | filters.regex(r"^setcat:-?\d+$"))
async def cb_setcat(client: Bot, call: CallbackQuery):
    channel_id = int(call.data.split(":", 1)[1])
    channel = await get_channel(channel_id) or {}
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎌 Anime", callback_data=f"setcatpick:{channel_id}:anime"),
        InlineKeyboardButton("🎬 Drama", callback_data=f"setcatpick:{channel_id}:drama"),
    ]])
    await call.answer()
    await call.message.edit_text(f"<b>{esc(channel.get('title', channel_id))}</b>\nSet category to:", reply_markup=kb)


@Bot.on_callback_query(filters.regex(r"^setcatpick:"))
async def cb_setcatpick(client: Bot, call: CallbackQuery):
    _, channel_id, category = call.data.split(":")
    channel_id = int(channel_id)
    await set_channel_category(channel_id, category)
    channel = await get_channel(channel_id) or {}
    await call.answer("Updated.")
    await call.message.edit_text(f"✅ <b>{esc(channel.get('title', channel_id))}</b> set to {category}.")


@Bot.on_message(filters.command("moveall") & is_admin_filter)
async def cmd_moveall(client: Bot, message: Message):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎌 Move all to Anime", callback_data="moveall:anime"),
        InlineKeyboardButton("🎬 Move all to Drama", callback_data="moveall:drama"),
    ]])
    await message.reply_text("Move every uncategorized channel to:", reply_markup=kb)


@Bot.on_callback_query(filters.regex(r"^moveall:"))
async def cb_moveall(client: Bot, call: CallbackQuery):
    category = call.data.split(":", 1)[1]
    count = await move_uncategorized(category)
    await call.answer("Done.")
    await call.message.edit_text(f"✅ Moved {count} previously-uncategorized channel(s) to {category}.")


# ---------------- Flat link lists ----------------
@Bot.on_message(filters.command(["links", "channelslist"]) & is_admin_filter)
async def cmd_links(client: Bot, message: Message):
    channels = await get_channels(None)
    if not channels:
        await message.reply_text("No channels registered yet.")
        return
    lines = ["<b>Registered Channels:</b>\n"]
    for c in channels:
        link = f"https://t.me/{client.username}?start={c['join_code']}" if c.get("join_code") else "-"
        lines.append(f"<b>{esc(c.get('title', c['_id']))}</b>\n{esc(link)}\n")
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


@Bot.on_message(filters.command("ch_links") & is_admin_filter)
async def cmd_ch_links(client: Bot, message: Message):
    channels = await get_channels(None)
    if not channels:
        await message.reply_text("No channels registered yet.")
        return
    lines = ["<b>Raw Channel Links:</b>\n"]
    for c in channels:
        link = c.get("invite_link") or channel_link_fallback(c["_id"])
        lines.append(f"<b>{esc(c.get('title', c['_id']))}</b> (<code>{c['_id']}</code>)\n{esc(link)}\n")
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


# ---------------- /reqlink -- one fresh instant join-request link ----------------
@Bot.on_message(filters.command("reqlink") & is_admin_filter)
async def cmd_reqlink(client: Bot, message: Message):
    channels = await get_channels(None)
    if not channels:
        await message.reply_text("No channels registered yet.")
        return
    rows = [[InlineKeyboardButton(c.get("title", str(c["_id"]))[:40], callback_data=f"reqlink:{c['_id']}")] for c in channels]
    await message.reply_text("Pick a channel to get a fresh join-request link:", reply_markup=InlineKeyboardMarkup(rows))


@Bot.on_callback_query(filters.regex(r"^reqlink:"))
async def cb_reqlink(client: Bot, call: CallbackQuery):
    channel_id = int(call.data.split(":", 1)[1])
    try:
        expire_dt = datetime.now() + timedelta(seconds=DEFAULT_LINK_EXPIRY_SECONDS)
        invite = await client.create_chat_invite_link(
            chat_id=channel_id,
            name=f"reqlink-{call.from_user.id}-{int(expire_dt.timestamp())}"[:32],
            expire_date=expire_dt,
            creates_join_request=True,
        )
    except Exception as e:
        await call.answer(f"❌ Failed: {e}", show_alert=True)
        return
    await call.answer()
    await client.send_message(call.message.chat.id, f"🔗 Fresh join-request link (valid {DEFAULT_LINK_EXPIRY_SECONDS // 60} min):\n{invite.invite_link}")


# ---------------- /genlink (postlink) -- specific post, reply to forward ----------------
@Bot.on_message(filters.command(["genlink", "postlink"]) & is_admin_filter)
async def cmd_genlink(client: Bot, message: Message):
    chat, msg_id, error = await _forwarded_source(message)
    if error:
        await message.reply_text(error)
        return
    if not await get_channel(chat.id):
        await message.reply_text(f"❌ This channel isn't registered yet.\nID: <code>{chat.id}</code>\n\nUse /add first.")
        return
    post_code = "P" + generate_code(5)
    await save_post(post_code, chat.id, msg_id)
    await message.reply_text(f"✅ Post saved!\n\n🆔 Code: <code>{post_code}</code>\n🔗 Link:\nhttps://t.me/{client.username}?start={post_code}")


@Bot.on_message(filters.command("bulklink") & is_admin_filter)
async def cmd_bulklink(client: Bot, message: Message):
    chat, msg_id, error = await _forwarded_source(message)
    if error:
        await message.reply_text(error)
        return
    if not await get_channel(chat.id):
        await message.reply_text(f"❌ This channel isn't registered yet.\nID: <code>{chat.id}</code>\n\nUse /add first.")
        return
    args = message.text.split()
    count = int(args[1]) if len(args) >= 2 and args[1].isdigit() else 5
    count = max(1, min(count, 50))
    lines = [f"✅ Generated {count} link(s) for the same post:\n"]
    for _ in range(count):
        post_code = "P" + generate_code(5)
        await save_post(post_code, chat.id, msg_id)
        lines.append(f"<code>{post_code}</code> -- https://t.me/{client.username}?start={post_code}")
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


@Bot.on_message(filters.command("delpostlink") & is_admin_filter)
async def cmd_delpostlink(client: Bot, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("Usage: <code>/delpostlink CODE</code>")
        return
    code = args[1].strip().upper()
    if await delete_post(code):
        await message.reply_text(f"✅ Link <code>{code}</code> has been deleted.")
    else:
        await message.reply_text("❌ No such post code found.")
