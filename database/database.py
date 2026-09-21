"""Async MongoDB access layer (motor). Merges the data model of both source
bots: per-channel category (anime/drama/None) + permanent join code from the
telebot version, and the channel/post/request separation from the Pyrogram
version.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

import motor.motor_asyncio

from config import DB_URI, DB_NAME

_client = motor.motor_asyncio.AsyncIOMotorClient(DB_URI, serverSelectionTimeoutMS=10000)
db = _client[DB_NAME]

users_col = db["users"]
admins_col = db["admins"]
channels_col = db["channels"]        # _id: channel_id
posts_col = db["posts"]              # _id: post_code
requests_col = db["requests"]        # _id: invite_link
settings_col = db["settings"]        # _id: key
autoforward_col = db["autoforward"]  # _id: source_channel_id
autopost_col = db["autopost"]        # _id: source_channel_id


async def ensure_indexes() -> None:
    await channels_col.create_index("category")
    await posts_col.create_index("channel_id")
    await requests_col.create_index("created_at")


# ---------------- Users ----------------
async def add_user(user_id: int) -> bool:
    existing = await users_col.find_one({"_id": user_id})
    if existing:
        return False
    await users_col.insert_one({"_id": user_id, "created_at": datetime.utcnow()})
    return True


async def full_userbase() -> List[int]:
    return [doc["_id"] async for doc in users_col.find({}, {"_id": 1})]


async def user_count() -> int:
    return await users_col.count_documents({})


# ---------------- Admins ----------------
async def is_admin_db(user_id: int) -> bool:
    return bool(await admins_col.find_one({"_id": user_id}))


async def add_admin(user_id: int) -> bool:
    result = await admins_col.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)
    return bool(result.upserted_id) or result.matched_count == 0


async def remove_admin(user_id: int) -> bool:
    result = await admins_col.delete_one({"_id": user_id})
    return result.deleted_count > 0


async def list_admins() -> List[int]:
    return [doc["_id"] async for doc in admins_col.find({}, {"_id": 1})]


# ---------------- Channels ----------------
async def save_channel(
    channel_id: int,
    title: str,
    category: Optional[str] = None,
    join_code: Optional[str] = None,
    invite_link: Optional[str] = None,
) -> None:
    set_fields: Dict[str, Any] = {"title": title, "updated_at": datetime.utcnow()}
    if category is not None:
        set_fields["category"] = category
    if join_code is not None:
        set_fields["join_code"] = join_code
    if invite_link is not None:
        set_fields["invite_link"] = invite_link
    await channels_col.update_one(
        {"_id": channel_id},
        {"$set": set_fields, "$setOnInsert": {"approve": True, "added_at": datetime.utcnow()}},
        upsert=True,
    )


async def get_channel(channel_id: int) -> Optional[dict]:
    return await channels_col.find_one({"_id": channel_id})


async def get_channel_by_join_code(join_code: str) -> Optional[dict]:
    return await channels_col.find_one({"join_code": join_code})


async def get_channels(category: Optional[str] = None) -> List[dict]:
    query: Dict[str, Any] = {}
    if category == "anime":
        query = {"category": "anime"}
    elif category == "drama":
        query = {"category": "drama"}
    # category None / "all" -> every channel
    return await channels_col.find(query).to_list(None)


async def delete_channel(channel_id: int) -> bool:
    result = await channels_col.delete_one({"_id": channel_id})
    await posts_col.delete_many({"channel_id": channel_id})
    return result.deleted_count > 0


async def set_channel_category(channel_id: int, category: str) -> None:
    await channels_col.update_one({"_id": channel_id}, {"$set": {"category": category}})


async def move_uncategorized(category: str) -> int:
    result = await channels_col.update_many(
        {"category": {"$exists": False}}, {"$set": {"category": category}}
    )
    return result.modified_count


async def set_channel_approve(channel_id: int, approve: bool) -> None:
    await channels_col.update_one({"_id": channel_id}, {"$set": {"approve": approve}})


# ---------------- Posts (per-post permanent link codes) ----------------
async def save_post(post_code: str, channel_id: int, message_id: Optional[int]) -> None:
    await posts_col.update_one(
        {"_id": post_code},
        {"$set": {"channel_id": channel_id, "message_id": message_id, "created_at": datetime.utcnow()}},
        upsert=True,
    )


async def get_post(post_code: str) -> Optional[dict]:
    return await posts_col.find_one({"_id": post_code})


async def get_posts_for_channel(channel_id: int) -> List[dict]:
    return await posts_col.find({"channel_id": channel_id}).to_list(None)


async def delete_post(post_code: str) -> bool:
    result = await posts_col.delete_one({"_id": post_code})
    return result.deleted_count > 0


# ---------------- Join requests (bot-issued links awaiting approval) ----------------
async def save_request(invite_link: str, post_code: Optional[str], channel_id: int, user_id: int) -> None:
    await requests_col.update_one(
        {"_id": invite_link},
        {"$set": {
            "post_code": post_code, "channel_id": channel_id, "user_id": user_id,
            "created_at": datetime.utcnow(),
        }},
        upsert=True,
    )


async def get_request(invite_link: str) -> Optional[dict]:
    return await requests_col.find_one({"_id": invite_link})


async def delete_request(invite_link: str) -> None:
    await requests_col.delete_one({"_id": invite_link})


async def delete_expired_requests(cutoff: datetime) -> int:
    result = await requests_col.delete_many({"created_at": {"$lt": cutoff}})
    return result.deleted_count


# ---------------- Settings (global key/value) ----------------
async def get_setting(key: str, default):
    row = await settings_col.find_one({"_id": key})
    return row["value"] if row else default


async def set_setting(key: str, value) -> None:
    await settings_col.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)


# ---------------- Auto-forward (source channel -> N target channels) ----------------
async def save_autoforward_targets(source_id: int, title: str, targets: List[dict]) -> None:
    await autoforward_col.update_one(
        {"_id": source_id},
        {"$set": {"title": title, "targets": targets, "updated_at": datetime.utcnow()}},
        upsert=True,
    )


async def get_autoforward(source_id: int) -> Optional[dict]:
    return await autoforward_col.find_one({"_id": source_id})


async def delete_autoforward(source_id: int) -> None:
    await autoforward_col.delete_one({"_id": source_id})


async def list_autoforward() -> List[dict]:
    return await autoforward_col.find({}).to_list(None)


# ---------------- Auto-post (title-keyword routing) ----------------
async def add_autopost_source(source_id: int, title: str) -> None:
    await autopost_col.update_one(
        {"_id": source_id}, {"$set": {"title": title, "added_at": datetime.utcnow()}}, upsert=True
    )


async def remove_autopost_source(source_id: int) -> bool:
    result = await autopost_col.delete_one({"_id": source_id})
    return result.deleted_count > 0


async def is_autopost_source(source_id: int) -> bool:
    return bool(await autopost_col.find_one({"_id": source_id}))


async def list_autopost_sources() -> List[dict]:
    return await autopost_col.find({}).to_list(None)
