# config.py -- all settings come from environment variables.
#
# Compatible with a generic bot-hoster / bot-deployer platform that runs
# this bot as a child process in polling mode (no web server, no PORT
# needed) and feeds it a per-bot .env file. See README.md for the full
# list of variables.

import os
import sys
import logging
from logging.handlers import RotatingFileHandler


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"❌ Missing required environment variable: {name}")
        sys.exit(1)
    return value


def _require_int(name: str) -> int:
    raw = _require(name)
    try:
        return int(raw)
    except ValueError:
        print(f"❌ Environment variable {name} must be a number, got: {raw!r}")
        sys.exit(1)


# ---- Required ----
BOT_TOKEN = _require("BOT_TOKEN")
API_ID = _require_int("API_ID")
API_HASH = _require("API_HASH")
OWNER_ID = _require_int("OWNER_ID")
DB_URI = _require("DB_URI")

# ---- Optional ----
DB_NAME = os.environ.get("DB_NAME", "Alizenx")
TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "20"))

# Extra admins besides OWNER_ID, space-separated user IDs. OWNER_ID is
# always an admin and cannot be removed via /deladmin.
try:
    ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split()]
except ValueError:
    print("❌ ADMINS must be space-separated numeric user IDs.")
    sys.exit(1)
if OWNER_ID not in ADMINS:
    ADMINS.append(OWNER_ID)

# How long a bot-issued join-request link stays valid, in seconds.
# Overridable at runtime with /reqtime.
DEFAULT_LINK_EXPIRY_SECONDS = int(os.environ.get("DEFAULT_LINK_EXPIRY_SECONDS", "300"))

# Optional: a channel/user the bot DMs on unhandled errors and crash-y
# events. Leave blank to disable.
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID", "").strip()
LOG_CHANNEL_ID = int(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None

# Extra "join our updates" button shown on approval messages. Optional.
EXTRA_BUTTON_LABEL = os.environ.get("EXTRA_BUTTON_LABEL", "• JOIN MY UPDATES •")
EXTRA_BUTTON_URL = os.environ.get("EXTRA_BUTTON_URL", "").strip()  # blank = button hidden

# Text customization
WELCOME_TEXT = os.environ.get(
    "WELCOME_TEXT",
    "<b>Welcome to the Link Sharing Bot!</b>\n\n"
    "Use the buttons below, or ask the owner for access to channels.",
)
ABOUT_TEXT = os.environ.get(
    "ABOUT_TEXT",
    "<b>About this bot</b>\n\nInstant, self-service access to shared Telegram channels.",
)

LOG_FILE_NAME = "linkbot.txt"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler(LOG_FILE_NAME, maxBytes=20_000_000, backupCount=3),
        logging.StreamHandler(),
    ],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)


def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
