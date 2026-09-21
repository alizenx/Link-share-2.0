from pyrogram import filters
from pyrogram.types import Message

from bot import Bot
from config import LOGGER, OWNER_ID
from database.database import (
    save_autoforward_targets, get_autoforward, delete_autoforward, list_autoforward,
    add_autopost_source, remove_autopost_source, list_autopost_sources, get_channels,
)
from helper_func import esc, is_admin_filter

logger = LOGGER(__name__)


@Bot.on_message(filters.command("autoforward") & is_admin_filter)
async def cmd_autoforward(client: Bot, message: Message):
    args = message.text.split()[1:]
    if len(args) < 2:
        await message.reply_text(
            "Usage: <code>/autoforward db_channel_id target_id_1 [target_id_2 ...]</code>\n\n"
            "⚠️ Bot must be a member (ideally admin) in the source channel, and admin "
            "with 'Post Messages' permission in every target."
        )
        return
    try:
        source_id = int(args[0])
        target_ids = [int(x) for x in args[1:]]
    except ValueError:
        await message.reply_text("❌ All IDs must be numeric, e.g. -1001234567890.")
        return

    warnings = []
    try:
        source_chat = await client.get_chat(source_id)
        source_title = source_chat.title or str(source_id)
    except Exception as e:
        await message.reply_text(f"❌ Bot can't access the source channel <code>{source_id}</code>: {esc(e)}")
        return

    targets = []
    for tid in target_ids:
        try:
            chat = await client.get_chat(tid)
            targets.append({"id": tid, "title": chat.title or str(tid)})
        except Exception as e:
            targets.append({"id": tid, "title": str(tid)})
            warnings.append(f"⚠️ Bot can't access target <code>{tid}</code>: {esc(e)}")

    existing = await get_autoforward(source_id)
    merged = {t["id"]: t for t in (existing.get("targets", []) if existing else [])}
    for t in targets:
        merged[t["id"]] = t
    await save_autoforward_targets(source_id, source_title, list(merged.values()))

    target_list = "\n".join(f"• {esc(t['title'])} (<code>{t['id']}</code>)" for t in merged.values())
    warning_block = ("\n\n" + "\n".join(warnings)) if warnings else ""
    await message.reply_text(
        f"✅ Auto-forwarding ON\n\n📥 Source: {esc(source_title)} (<code>{source_id}</code>)\n"
        f"📤 Targets:\n{target_list}{warning_block}"
    )


@Bot.on_message(filters.command("stopautoforward") & is_admin_filter)
async def cmd_stopautoforward(client: Bot, message: Message):
    args = message.text.split()[1:]
    if len(args) < 1 or not args[0].lstrip("-").isdigit():
        await message.reply_text("Usage: <code>/stopautoforward db_channel_id [target_channel_id]</code>")
        return
    source_id = int(args[0])
    config = await get_autoforward(source_id)
    if not config:
        await message.reply_text("❌ No auto-forwarding set for this source channel.")
        return

    if len(args) >= 2 and args[1].lstrip("-").isdigit():
        target_id = int(args[1])
        remaining = [t for t in config.get("targets", []) if t["id"] != target_id]
        if len(remaining) == len(config.get("targets", [])):
            await message.reply_text("❌ That target wasn't set for this source channel.")
            return
        if remaining:
            await save_autoforward_targets(source_id, config.get("title", str(source_id)), remaining)
            await message.reply_text(f"✅ Removed target <code>{target_id}</code>. Remaining targets still active.")
        else:
            await delete_autoforward(source_id)
            await message.reply_text("✅ That was the last target -- auto-forwarding fully stopped.")
    else:
        await delete_autoforward(source_id)
        await message.reply_text(f"✅ Auto-forwarding stopped: {esc(config.get('title', source_id))}")


@Bot.on_message(filters.command("listautoforward") & is_admin_filter)
async def cmd_listautoforward(client: Bot, message: Message):
    configs = await list_autoforward()
    if not configs:
        await message.reply_text("No auto-forwarding set up yet.")
        return
    lines = ["<b>🔄 Auto-Forwarding List:</b>\n"]
    for c in configs:
        lines.append(f"📥 <b>{esc(c.get('title', c['_id']))}</b> (<code>{c['_id']}</code>)")
        for t in c.get("targets", []):
            lines.append(f"   ↳ 📤 {esc(t['title'])} (<code>{t['id']}</code>)")
        lines.append("")
    await message.reply_text("\n".join(lines))


# ---------------- Auto-post: route by registered-channel title match ----------------
@Bot.on_message(filters.command("addautopost") & is_admin_filter)
async def cmd_addautopost(client: Bot, message: Message):
    replied = message.reply_to_message
    if replied is None or replied.forward_from_chat is None:
        await message.reply_text("❌ Forward a post from the SOURCE channel here, then reply to it with /addautopost.")
        return
    chat = replied.forward_from_chat
    await add_autopost_source(chat.id, chat.title or str(chat.id))
    await message.reply_text(f"✅ Auto-post source added: {esc(chat.title or chat.id)}")


@Bot.on_message(filters.command("delautopost") & is_admin_filter)
async def cmd_delautopost(client: Bot, message: Message):
    args = message.text.split()
    if len(args) != 2 or not args[1].lstrip("-").isdigit():
        await message.reply_text("Usage: <code>/delautopost source_channel_id</code>")
        return
    if await remove_autopost_source(int(args[1])):
        await message.reply_text("✅ Auto-post source removed.")
    else:
        await message.reply_text("❌ Not found.")


@Bot.on_message(filters.command("listautopost") & is_admin_filter)
async def cmd_listautopost(client: Bot, message: Message):
    sources = await list_autopost_sources()
    if not sources:
        await message.reply_text("No auto-post sources set yet.")
        return
    lines = ["<b>🎯 Auto Post Sources:</b>\n"]
    for s in sources:
        lines.append(f"📥 {esc(s.get('title', s['_id']))} (<code>{s['_id']}</code>)")
    await message.reply_text("\n".join(lines))


# ---------------- The actual channel_post engine ----------------
@Bot.on_message(filters.channel)
async def handle_channel_post(client: Bot, message: Message):
    source_id = message.chat.id

    # 1) Title-keyword auto-post: copy to any registered channel whose title
    #    (3+ chars, to avoid false matches) appears in this post's text.
    sources = {s["_id"] for s in await list_autopost_sources()}
    if source_id in sources:
        text = (message.text or message.caption or "")
        if text:
            text_lower = text.lower()
            for c in await get_channels(None):
                title = (c.get("title") or "").strip()
                if len(title) >= 3 and title.lower() in text_lower and c["_id"] != source_id:
                    try:
                        await message.copy(c["_id"])
                    except Exception as e:
                        logger.info(f"Auto-post copy to {c['_id']} failed: {e}")

    # 2) Fixed source -> target(s) auto-forward.
    config = await get_autoforward(source_id)
    if config and config.get("targets"):
        for target in config["targets"]:
            try:
                await message.forward(target["id"])
            except Exception as e:
                logger.error(f"Auto-forward failed ({source_id} -> {target['id']}): {e}")
                try:
                    await client.send_message(
                        OWNER_ID,
                        f"⚠️ Auto-forward failed\n📥 Source: <code>{source_id}</code>\n"
                        f"📤 Target: <code>{target['id']}</code>\nError: {esc(e)}",
                    )
                except Exception:
                    pass
