import asyncio
from datetime import datetime

from pyrogram import Client
from pyrogram.enums import ParseMode

from config import API_HASH, API_ID, BOT_TOKEN, TG_BOT_WORKERS, OWNER_ID, LOGGER
from database.database import ensure_indexes, delete_expired_requests
from config import DEFAULT_LINK_EXPIRY_SECONDS

logger = LOGGER(__name__)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="LinkBot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            in_memory=True,  # no .session file needed for a hosted child bot
        )

    async def start(self):
        await super().start()
        await ensure_indexes()
        me = await self.get_me()
        self.username = me.username
        self.uptime = datetime.now()
        self.set_parse_mode(ParseMode.HTML)

        try:
            await self.send_message(OWNER_ID, "<b>🤖 Bot restarted and is now online.</b>")
        except Exception as e:
            logger.warning(f"Could not DM owner ({OWNER_ID}) on start: {e}")

        asyncio.create_task(self._expired_requests_cleaner())
        logger.info(f"Bot running as @{self.username}")

    async def _expired_requests_cleaner(self):
        """Background loop: drop stale join-request records so /status and
        lookups don't accumulate garbage. Does not touch Telegram itself --
        Telegram expires the invite link on its own side too."""
        while True:
            try:
                cutoff = datetime.utcnow()
                # requests created more than the max sane window ago (1 day)
                # are almost certainly abandoned regardless of the current
                # /reqtime setting, so use a fixed generous cutoff here.
                from datetime import timedelta
                await delete_expired_requests(cutoff - timedelta(days=1))
            except Exception as e:
                logger.error(f"Expired-request cleanup failed: {e}")
            await asyncio.sleep(3600)

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped.")
