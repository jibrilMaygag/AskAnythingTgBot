# AskAnything Telegram Bot

A production-style, scalable Telegram Q&A community bot built with `python-telegram-bot` v21 and MongoDB (Motor async driver).

---

## Architecture

```
AskAnythingTgBot/
├── main.py           # App entry point, handler registration, job queue
├── config.py         # All env-var config in one place
├── states.py         # Conversation state constants + in-memory session stores
├── database.py       # Async MongoDB CRUD layer (Motor)
├── utils.py          # Rendering helpers, keyboard builders, send helpers
├── start.py          # /start command + deep-link routing
├── buttons.py        # All CallbackQuery handling
├── messages.py       # Text/photo message handling (state machine)
├── notifications.py  # Notification delivery (new reply, rep changes)
├── admin.py          # Admin commands + moderation callbacks
├── analytics.py      # Stats dashboard, daily snapshot job
├── requirements.txt
├── .env.example
└── README.md
```

---

## Features

| Feature | Status |
|---|---|
| Auto-created default profile (Anonymous) | ✅ |
| Display name + gender emoji (👨/👩) | ✅ |
| Profile image (Telegram file_id) | ✅ |
| Reputation system (votes, answers, questions) | ✅ |
| MongoDB persistence (all collections) | ✅ |
| Image support on questions & replies | ✅ |
| Paginated reply viewer (Show More / Show All) | ✅ |
| Telegram-native reply threading (reply_to_message_id) | ✅ |
| New-reply notifications | ✅ |
| Relative timestamps (5m ago, 2h ago…) | ✅ |
| Search with text-index + pagination | ✅ |
| Trending questions (by reply count) | ✅ |
| Reputation leaderboard | ✅ |
| Admin panel: ban/unban/mute/delete/reports | ✅ |
| Analytics snapshot (daily job to admins) | ✅ |
| Scalable DB schema (future web dashboard ready) | ✅ |

---

## Setup

### 1. Clone & install

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Fill in BOT_TOKEN, BOT_USERNAME, CHANNEL_USERNAME, CHANNEL_ID, ADMIN_IDS, MONGO_URI
```

### 3. MongoDB

Start a local MongoDB instance or use MongoDB Atlas.
The bot creates all indexes automatically on first run.

### 4. Run

```bash
python main.py
```

---

## Deep Links

| URL | Effect |
|---|---|
| `t.me/YourBot?start=show_<question_id>` | Opens question with paginated replies |
| `t.me/YourBot?start=answer_<question_id>` | Opens direct reply flow |

---

## MongoDB Collections

| Collection | Purpose |
|---|---|
| `users` | Profile, reputation, timestamps, ban/mute status |
| `questions` | Text, image, topic, channel post URL, reply count |
| `replies` | Text, image, parent chain, telegram message ID |
| `votes` | Per-user vote per target, direction |
| `reports` | Flagged content, resolution tracking |
| `notifications` | Inbox per user, read flag |
| `analytics` | Event counters keyed by date + event name |

---

## Admin Commands

```
/admin          Admin panel
/stats          Engagement snapshot
/reports        List 10 pending reports
/ban <id>       Ban user
/unban <id>     Unban user
/mute <id> [h]  Mute user (default 24h)
/unmute <id>    Unmute user
```

---

## Reputation Weights (config.py)

| Event | Delta |
|---|---|
| Upvote received | +5 |
| Downvote received | -2 |
| Answer posted | +2 |
| Question posted | +1 |

---

## Extending

- **New reputation source**: add a call to `db.adjust_reputation()` wherever the event fires.
- **New notification type**: add a formatter + delivery function in `notifications.py`.
- **Web dashboard**: all data is in MongoDB with consistent schemas; wire up a FastAPI/Flask layer on top of `database.py`.
- **Redis sessions**: replace the `user_state` / `user_data` dicts in `states.py` with a Redis-backed store for multi-instance deployments.
