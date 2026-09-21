import math
import string

from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot import Bot
from database.database import get_channels
from helper_func import esc

LABEL = {"anime": "🎌 Anime", "drama": "🎬 Drama", "all": "📋 All"}
PER_PAGE = 10


def letter_key(title: str) -> str:
    first = title.strip()[:1].upper()
    return first if first.isalpha() else "#"


def menu_content(category: str = None):
    if category not in ("anime", "drama", "all"):
        text = "📚 <b>CHANNEL INDEX</b>\n\nChoose a category:"
        rows = [
            [InlineKeyboardButton("🎌 Anime", callback_data="idx:menu:anime"),
             InlineKeyboardButton("🎬 Drama", callback_data="idx:menu:drama")],
            [InlineKeyboardButton("📋 All", callback_data="idx:menu:all")],
            [InlineKeyboardButton("❌ Close", callback_data="idx:close")],
        ]
        return text, InlineKeyboardMarkup(rows)

    text = f"📚 <b>{LABEL[category]} INDEX</b>\n\nPick a letter:"
    letters = list(string.ascii_uppercase) + ["#"]
    rows = [
        [InlineKeyboardButton(letters[i], callback_data=f"idx:letter:{category}:{letters[i]}:1")
         for i in range(row, min(row + 6, len(letters)))]
        for row in range(0, len(letters), 6)
    ]
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="idx:menu:root"), InlineKeyboardButton("❌ Close", callback_data="idx:close")])
    return text, InlineKeyboardMarkup(rows)


async def letter_content(client: Bot, category: str, letter: str, page: int):
    channels = await get_channels(None if category == "all" else category)
    matches = sorted(
        (c for c in channels if letter_key(c.get("title", "")) == letter),
        key=lambda c: (c.get("title") or "").lower(),
    )
    header = f"📚 <b>{LABEL[category]} INDEX</b> — {letter}\n\n"
    if not matches:
        rows = [[InlineKeyboardButton("🔙 Back", callback_data=f"idx:menu:{category}"), InlineKeyboardButton("❌ Close", callback_data="idx:close")]]
        return header + "No channels yet under this letter.", InlineKeyboardMarkup(rows)

    total_pages = max(1, math.ceil(len(matches) / PER_PAGE))
    page = max(1, min(page, total_pages))
    page_items = matches[(page - 1) * PER_PAGE: page * PER_PAGE]
    lines = []
    for c in page_items:
        link = f"https://t.me/{client.username}?start={c['join_code']}" if c.get("join_code") else "#"
        lines.append(f"✦ <a href=\"{esc(link)}\">{esc(c.get('title', c['_id']))}</a>")
    body = "\n".join(lines)
    footer = f"\n\n📁 Page {page}/{total_pages} — Total: {len(matches)}"

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"idx:letter:{category}:{letter}:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"idx:letter:{category}:{letter}:{page + 1}"))
    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton("🔙 Back", callback_data=f"idx:menu:{category}"), InlineKeyboardButton("❌ Close", callback_data="idx:close")])
    return header + body + footer, InlineKeyboardMarkup(rows)


@Bot.on_message(filters.command("index"))
async def cmd_index(client: Bot, message: Message):
    args = message.text.split()
    category = args[1].lower() if len(args) >= 2 else None
    text, kb = menu_content(category)
    await message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


@Bot.on_callback_query(filters.regex(r"^idx:menu:"))
async def cb_idx_menu(client: Bot, call: CallbackQuery):
    category = call.data.split(":", 2)[2]
    category = None if category == "root" else category
    text, kb = menu_content(category)
    await call.answer()
    try:
        await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await call.message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)


@Bot.on_callback_query(filters.regex(r"^idx:letter:"))
async def cb_idx_letter(client: Bot, call: CallbackQuery):
    _, _, category, letter, page = call.data.split(":")
    text, kb = await letter_content(client, category, letter, int(page))
    await call.answer()
    await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)


@Bot.on_callback_query(filters.regex(r"^idx:close$"))
async def cb_idx_close(client: Bot, call: CallbackQuery):
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
