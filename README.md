# LinkBot -- merged & hardened

Ye dono purane bots (`Links-Share-Bot` aur `LinkProviderbot`) ka merged, bug-fixed
version hai — Pyrogram/Pyrofork + MongoDB (motor, async), plugin-based structure,
tumhare bot-hoster panel ke saath deploy karne ke liye ready.

## Bot-hoster mein deploy karna
1. Poora folder ZIP karke apne bot-hoster bot ko `.py`/`.zip` upload flow se
   ya `/github` command se bhejo (agar GitHub pe daala hai).
2. `requirements.txt` khud install ho jayegi (host isko detect karta hai).
3. Jab host `.env` maange, `.env.example` jaisi values bhar do — neeche
   sabki explanation hai.
4. Koi PORT/web-server ki zaroorat nahi — bot polling mode mein chalta hai,
   jaisa tumhare host ke child bots ke liye zaroori hai.

## Environment variables
| Variable | Zaroori? | Kya hai |
|---|---|---|
| `BOT_TOKEN` | Haan | @BotFather se |
| `API_ID`, `API_HASH` | Haan | my.telegram.org se |
| `OWNER_ID` | Haan | tumhari Telegram user ID |
| `DB_URI` | Haan | MongoDB connection string |
| `ADMINS` | Nahi | space-separated extra admin IDs |
| `DB_NAME` | Nahi | default `linkbot` |
| `DEFAULT_LINK_EXPIRY_SECONDS` | Nahi | default 300 (5 min) |
| `LOG_CHANNEL_ID` | Nahi | error alerts ke liye |
| `EXTRA_BUTTON_URL`/`LABEL` | Nahi | approval message pe extra button |
| `WELCOME_TEXT`, `ABOUT_TEXT` | Nahi | customizable |

Koi bhi required variable missing ho to bot turant clear error print karke
exit ho jata hai — silent crash nahi hota.

## Feature list (dono bots se merged)
- Multi-channel registration with categories (Anime/Drama/uncategorized):
  `/add`, `/addanime`, `/adddrama`, `/setcategory`, `/moveall`
- Paginated browsing: `/channels`, `/animechannel`, `/dramachannel`, public
  `/index` (A-Z, koi bhi user use kar sakta hai)
- Links: `/links`, `/ch_links`, `/reqlink`, `/genlink` (`/postlink`),
  `/bulklink <count>`, `/delpostlink <code>`
- Auto-approve join requests (bot-issued links only): `/reqtime`, `/reqmode`,
  `/approveon`, `/approveoff`
- Admin management (owner-only): `/addadmin`, `/deladmin`, `/admins`
- Real channel-admin promotion (owner-only): `/adminme`, `/adminmeall`
- Broadcast: `/broadcast`, `/tbroadcast`, `/cbalanced`, `/tcbalanced`
- Auto-forward + title-keyword auto-post: `/autoforward`,
  `/stopautoforward`, `/listautoforward`, `/addautopost`, `/delautopost`,
  `/listautopost`
- `/status`, inline admin panel (`/start` par admin ko button milta hai)

## Fixed from the original two bots
- **Removed hardcoded live secrets** and the hardcoded backdoor admin ID
  that both source files had.
- **`/adminme`, `/adminmeall`, `/addadmin`, `/deladmin` ab owner-only hain**
  — pehle koi bhi bot-admin kisi ko bhi real channel-owner-level permission
  de sakta tha.
- Removed dead/broken `get_user_client()`/`UserClient` code (undefined
  names, would crash if ever called).
- Removed the `id_pattern` `NameError` bug (CHAT_ID parsing) by dropping
  that whole config path — not needed with the new join-request model.
- Async MongoDB (`motor`) throughout instead of mixing sync `pymongo`
  calls inside an async framework — no more blocking the event loop.
- Dropped all in-memory "next step" wizard flows (the most bug-prone part
  of both originals) in favor of simple reply-to-forwarded-post commands —
  fewer moving parts, nothing to break across bot restarts.
- No web server / PORT dependency, since your host runs child bots in
  polling mode.
