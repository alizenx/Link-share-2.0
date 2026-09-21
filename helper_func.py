import random
import string
import html

from pyrogram.filters import Filter, create

from config import ADMINS, OWNER_ID
from database.database import is_admin_db


def generate_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def esc(text) -> str:
    """HTML-escape for safe use inside parse_mode=HTML messages."""
    return html.escape(str(text)) if text is not None else ""


def get_readable_time(seconds: int) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


async def _is_admin_user(user_id: int) -> bool:
    if user_id in ADMINS:
        return True
    return await is_admin_db(user_id)


async def _is_admin_filter_func(_, __, update):
    user = getattr(update, "from_user", None)
    if user is None:
        return False
    return await _is_admin_user(user.id)


async def _is_owner_filter_func(_, __, update):
    user = getattr(update, "from_user", None)
    if user is None:
        return False
    return user.id == OWNER_ID


# Usable on both Message and CallbackQuery updates (both expose from_user).
is_admin_filter: Filter = create(_is_admin_filter_func)
is_owner_filter: Filter = create(_is_owner_filter_func)
