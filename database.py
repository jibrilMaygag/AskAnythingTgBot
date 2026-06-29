"""
database.py – Async MongoDB persistence layer via Motor.

Collections
───────────
users          – profiles, reputation, timestamps
questions      – text, image, topic, channel post refs
replies        – text, image, parent chain, message refs
votes          – per-user votes on questions/replies
reports        – flagged content
notifications  – inbox items per user
analytics      – event counters & daily snapshots
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, TEXT

from config import (
    MONGO_URI, DB_NAME,
    REP_UPVOTE_RECEIVED, REP_DOWNVOTE_RECEIVED,
    REP_ANSWER_POSTED, REP_QUESTION_POSTED,
    REPLIES_PER_PAGE, SEARCH_PER_PAGE,
    LEADERBOARD_PER_PAGE, TRENDING_PER_PAGE,
)

logger = logging.getLogger(__name__)

# ── Singleton ─────────────────────────────────────────────────────────────────
_client: Optional[AsyncIOMotorClient] = None


def _db():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client[DB_NAME]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Index bootstrap ───────────────────────────────────────────────────────────
async def create_indexes() -> None:
    db = _db()
    await db.users.create_index("telegram_id", unique=True)
    await db.users.create_index([("reputation", DESCENDING)])
    await db.users.create_index("username")

    await db.questions.create_index([("created_at", DESCENDING)])
    await db.questions.create_index([("reply_count", DESCENDING)])
    await db.questions.create_index([("text", TEXT), ("topic", TEXT)])
    await db.questions.create_index([("author_id", ASCENDING), ("status", ASCENDING)])
    await db.questions.create_index([("status", ASCENDING)])
    await db.questions.create_index([("author_id", ASCENDING)])

    await db.replies.create_index("question_id")
    await db.replies.create_index([("author_id", ASCENDING)])
    await db.replies.create_index([("created_at", ASCENDING)])
    await db.replies.create_index("parent_reply_id")
    await db.replies.create_index([("author_id", ASCENDING), ("created_at", ASCENDING)])

    await db.votes.create_index([("target_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
    await db.votes.create_index("target_id")

    await db.reports.create_index([("target_id", ASCENDING), ("reporter_id", ASCENDING)], unique=True)
    await db.reports.create_index("resolved")

    await db.notifications.create_index("recipient_id")
    await db.notifications.create_index([("created_at", DESCENDING)])
    await db.notifications.create_index("read")

    await db.analytics.create_index([("date", DESCENDING)])
    await db.analytics.create_index("event")

    await db.admin_logs.create_index([("created_at", DESCENDING)])
    await db.admin_logs.create_index("action")

    logger.info("MongoDB indexes created.")


# ═════════════════════════════════════════════════════════════════════════════
# USERS
# ═════════════════════════════════════════════════════════════════════════════

async def get_user(telegram_id: int) -> Optional[dict]:
    return await _db().users.find_one({"telegram_id": telegram_id})


async def get_user_question_count(telegram_id: int) -> int:
    return await _db().questions.count_documents({"author_id": telegram_id, "is_deleted": False, "status": {"$in": ["approved", "pending", "rejected"]}})


async def get_user_reply_count(telegram_id: int) -> int:
    return await _db().replies.count_documents({"author_id": telegram_id, "is_deleted": False})


async def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> dict:
    """Upsert user. Always returns the user document."""
    db = _db()
    now = now_utc()
    result = await db.users.find_one_and_update(
        {"telegram_id": telegram_id},
        {
            "$setOnInsert": {
                "telegram_id": telegram_id,
                "display_name": "Anonymous",
                "first_name": first_name,
                "gender": None,           # "M" | "F" | None
                "reputation": 0,
                "is_banned": False,
                "is_muted": False,
                "muted_until": None,
                "created_at": now,
            },
            "$set": {
                "last_active": now,
                "username": username,
            },
        },
        upsert=True,
        return_document=True,
    )
    return result


async def update_user(telegram_id: int, **fields) -> dict:
    result = await _db().users.find_one_and_update(
        {"telegram_id": telegram_id},
        {"$set": fields},
        return_document=True,
    )
    return result


async def adjust_reputation(telegram_id: int, delta: int) -> int:
    """Atomically adjust reputation. Returns new value."""
    result = await _db().users.find_one_and_update(
        {"telegram_id": telegram_id},
        {"$inc": {"reputation": delta}},
        return_document=True,
    )
    return result["reputation"] if result else 0


async def get_leaderboard(page: int = 0) -> list[dict]:
    skip = page * LEADERBOARD_PER_PAGE
    cursor = _db().users.find(
        {"is_banned": {"$ne": True}},
        {"telegram_id": 1, "display_name": 1, "gender": 1, "reputation": 1,
         "username": 1}
    ).sort("reputation", DESCENDING).skip(skip).limit(LEADERBOARD_PER_PAGE)
    return await cursor.to_list(length=LEADERBOARD_PER_PAGE)


async def get_top_contributors(page: int = 0) -> list[dict]:
    """Users with most replies."""
    skip = page * LEADERBOARD_PER_PAGE
    pipeline = [
        {"$match": {"is_banned": {"$ne": True}}},
        {"$lookup": {
            "from": "replies",
            "localField": "telegram_id",
            "foreignField": "author_id",
            "as": "reply_docs",
        }},
        {"$project": {
            "telegram_id": 1,
            "display_name": 1,
            "gender": 1,
            "reputation": 1,
            "reply_count": {"$size": "$reply_docs"},
        }},
        {"$sort": {"reply_count": -1}},
        {"$skip": skip},
        {"$limit": LEADERBOARD_PER_PAGE},
    ]
    return await _db().users.aggregate(pipeline).to_list(length=LEADERBOARD_PER_PAGE)


# ═════════════════════════════════════════════════════════════════════════════
# QUESTIONS
# ═════════════════════════════════════════════════════════════════════════════

async def create_question(
    author_id: int,
    topic: str,
    text: str,
    image_file_id: str = None,
) -> dict:
    now = now_utc()
    doc = {
        "author_id": author_id,
        "topic": topic,
        "text": text,
        "image_file_id": image_file_id,
        "content_rating": "normal",
        "reply_count": 0,
        "channel_message_id": None,
        "channel_chat_id": None,
        "channel_post_url": None,
        "is_deleted": False,
        "status": "pending",
        "reviewed_by": None,
        "reviewed_at": None,
        "review_reason": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await _db().questions.insert_one(doc)
    doc["_id"] = result.inserted_id

    await _db().users.update_one(
        {"telegram_id": author_id},
        {"$inc": {"reputation": REP_QUESTION_POSTED}},
    )
    await _track_event("question_created")
    return doc


async def get_question(question_id: str | ObjectId, include_pending: bool = False) -> Optional[dict]:
    if isinstance(question_id, str):
        try:
            question_id = ObjectId(question_id)
        except Exception:
            return None
    filt = {"_id": question_id, "is_deleted": False}
    if not include_pending:
        filt["$or"] = [{"status": {"$exists": False}}, {"status": "approved"}]
    return await _db().questions.find_one(filt)


async def update_question(question_id: str | ObjectId, **fields) -> Optional[dict]:
    if isinstance(question_id, str):
        question_id = ObjectId(question_id)
    fields["updated_at"] = now_utc()
    return await _db().questions.find_one_and_update(
        {"_id": question_id},
        {"$set": fields},
        return_document=True,
    )


async def soft_delete_question(question_id: str | ObjectId) -> bool:
    if isinstance(question_id, str):
        question_id = ObjectId(question_id)
    res = await _db().questions.update_one(
        {"_id": question_id}, {"$set": {"is_deleted": True, "status": "deleted", "updated_at": now_utc()}}
    )
    return res.modified_count > 0


async def get_pending_questions(skip: int = 0, limit: int = 20) -> list[dict]:
    cursor = _db().questions.find(
        {"is_deleted": False, "status": "pending"}
    ).sort("created_at", ASCENDING).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def approve_question(question_id: str | ObjectId, admin_id: int, content_rating: str = "normal") -> Optional[dict]:
    if isinstance(question_id, str):
        question_id = ObjectId(question_id)
    if content_rating not in {"normal", "sensitive"}:
        content_rating = "normal"
    return await _db().questions.find_one_and_update(
        {"_id": question_id},
        {"$set": {"status": "approved", "content_rating": content_rating, "reviewed_by": admin_id, "reviewed_at": now_utc(), "review_reason": None, "updated_at": now_utc()}},
        return_document=True,
    )


async def reject_question(question_id: str | ObjectId, admin_id: int, reason: str = None) -> Optional[dict]:
    if isinstance(question_id, str):
        question_id = ObjectId(question_id)
    return await _db().questions.find_one_and_update(
        {"_id": question_id},
        {"$set": {"status": "rejected", "content_rating": "normal", "reviewed_by": admin_id, "reviewed_at": now_utc(), "review_reason": reason, "updated_at": now_utc()}},
        return_document=True,
    )


async def get_trending_questions(page: int = 0) -> tuple[list[dict], int]:
    skip = page * TRENDING_PER_PAGE
    filt = {"is_deleted": False, "$or": [{"status": {"$exists": False}}, {"status": "approved"}]}
    total = await _db().questions.count_documents(filt)
    cursor = _db().questions.find(filt).sort(
        "reply_count", DESCENDING
    ).skip(skip).limit(TRENDING_PER_PAGE)
    items = await cursor.to_list(length=TRENDING_PER_PAGE)
    return items, total


async def search_questions(query: str, page: int = 0) -> tuple[list[dict], int]:
    skip = page * SEARCH_PER_PAGE
    filt = {"$text": {"$search": query}, "is_deleted": False, "$or": [{"status": {"$exists": False}}, {"status": "approved"}]}
    total = await _db().questions.count_documents(filt)
    cursor = _db().questions.find(
        filt,
        {"score": {"$meta": "textScore"}},
    ).sort([("score", {"$meta": "textScore"})]).skip(skip).limit(SEARCH_PER_PAGE)
    items = await cursor.to_list(length=SEARCH_PER_PAGE)
    return items, total


# ═════════════════════════════════════════════════════════════════════════════
# REPLIES
# ═════════════════════════════════════════════════════════════════════════════

async def create_reply(
    question_id: str | ObjectId,
    author_id: int,
    text: str,
    parent_reply_id: str | ObjectId = None,
    image_file_id: str = None,
) -> dict:
    if isinstance(question_id, str):
        question_id = ObjectId(question_id)
    if isinstance(parent_reply_id, str) and parent_reply_id:
        parent_reply_id = ObjectId(parent_reply_id)

    now = now_utc()
    doc = {
        "question_id": question_id,
        "author_id": author_id,
        "text": text,
        "image_file_id": image_file_id,
        "parent_reply_id": parent_reply_id,
        "upvotes": 0,
        "downvotes": 0,
        "telegram_message_id": None,  # message ID in group/channel
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    result = await _db().replies.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Increment question reply count
    await _db().questions.update_one(
        {"_id": question_id},
        {"$inc": {"reply_count": 1}, "$set": {"updated_at": now}},
    )
    await _db().users.update_one(
        {"telegram_id": author_id},
        {"$inc": {"reputation": REP_ANSWER_POSTED}},
    )
    await _track_event("reply_created")
    return doc


async def get_reply(reply_id: str | ObjectId) -> Optional[dict]:
    if isinstance(reply_id, str):
        try:
            reply_id = ObjectId(reply_id)
        except Exception:
            return None
    return await _db().replies.find_one({"_id": reply_id, "is_deleted": False})


async def get_replies_for_question(
    question_id: str | ObjectId,
    offset: int = 0,
    limit: int = REPLIES_PER_PAGE,
    exclude_reply_id: str | ObjectId = None,
) -> tuple[list[dict], int]:
    if isinstance(question_id, str):
        question_id = ObjectId(question_id)
    filt = {"question_id": question_id, "is_deleted": False}
    if exclude_reply_id:
        if isinstance(exclude_reply_id, str):
            try:
                exclude_reply_id = ObjectId(exclude_reply_id)
            except Exception:
                exclude_reply_id = None
        if exclude_reply_id:
            filt["_id"] = {"$ne": exclude_reply_id}
    total = await _db().replies.count_documents(filt)
    cursor = _db().replies.find(filt).sort("created_at", ASCENDING).skip(offset).limit(limit)
    items = await cursor.to_list(length=limit)
    return items, total


async def update_reply(reply_id: str | ObjectId, **fields) -> Optional[dict]:
    """Update arbitrary fields on a reply document."""
    if isinstance(reply_id, str):
        try:
            reply_id = ObjectId(reply_id)
        except Exception:
            return None
    fields["updated_at"] = now_utc()
    return await _db().replies.find_one_and_update(
        {"_id": reply_id},
        {"$set": fields},
        return_document=True,
    )


async def soft_delete_reply(reply_id: str | ObjectId) -> bool:
    if isinstance(reply_id, str):
        reply_id = ObjectId(reply_id)
    res = await _db().replies.update_one(
        {"_id": reply_id}, {"$set": {"is_deleted": True, "updated_at": now_utc()}}
    )
    if res.modified_count:
        # Decrement parent question reply_count
        reply = await _db().replies.find_one({"_id": reply_id})
        if reply:
            await _db().questions.update_one(
                {"_id": reply["question_id"]}, {"$inc": {"reply_count": -1}}
            )
    return res.modified_count > 0


# ═════════════════════════════════════════════════════════════════════════════
# VOTES
# ═════════════════════════════════════════════════════════════════════════════

async def get_user_vote(target_id: str | ObjectId, user_id: int) -> Optional[str]:
    if isinstance(target_id, str):
        try:
            target_id = ObjectId(target_id)
        except Exception:
            return None
    doc = await _db().votes.find_one({"target_id": target_id, "user_id": user_id})
    return doc["direction"] if doc else None


async def has_report(target_id: str | ObjectId, user_id: int) -> bool:
    if isinstance(target_id, str):
        try:
            target_id = ObjectId(target_id)
        except Exception:
            return False
    doc = await _db().reports.find_one({"target_id": target_id, "reporter_id": user_id})
    return bool(doc)


async def cast_vote(
    target_id: str | ObjectId,
    target_type: str,       # "reply" | "question"
    user_id: int,
    direction: str,         # "up" | "down"
) -> tuple[bool, Optional[str]]:
    """
    Cast or change a vote.
    Returns (changed: bool, previous_direction: str | None).
    Side-effects: adjusts vote counts on target and reputation on author.
    """
    if isinstance(target_id, str):
        target_id = ObjectId(target_id)

    existing = await _db().votes.find_one({"target_id": target_id, "user_id": user_id})
    prev = existing["direction"] if existing else None

    if prev == direction:
        return False, prev   # Same vote – no change

    # Upsert vote record
    await _db().votes.update_one(
        {"target_id": target_id, "user_id": user_id},
        {"$set": {"direction": direction, "target_type": target_type, "voted_at": now_utc()}},
        upsert=True,
    )

    # Adjust counts on the target collection
    collection = _db().replies if target_type == "reply" else _db().questions
    inc = {}
    if prev == "up":
        inc["upvotes"] = -1
    elif prev == "down":
        inc["downvotes"] = -1
    if direction == "up":
        inc["upvotes"] = inc.get("upvotes", 0) + 1
    else:
        inc["downvotes"] = inc.get("downvotes", 0) + 1

    target_doc = await collection.find_one_and_update(
        {"_id": target_id}, {"$inc": inc}, return_document=True
    )

    # Adjust author reputation
    if target_doc:
        author_id = target_doc.get("author_id")
        if author_id and author_id != user_id:
            rep_delta = 0
            if direction == "up" and prev != "up":
                rep_delta += REP_UPVOTE_RECEIVED
            if direction == "down" and prev != "down":
                rep_delta += REP_DOWNVOTE_RECEIVED
            if prev == "up" and direction != "up":
                rep_delta -= REP_UPVOTE_RECEIVED
            if prev == "down" and direction != "down":
                rep_delta -= REP_DOWNVOTE_RECEIVED
            if rep_delta:
                await adjust_reputation(author_id, rep_delta)

    return True, prev


# ═════════════════════════════════════════════════════════════════════════════
# REPORTS
# ═════════════════════════════════════════════════════════════════════════════

async def add_report(
    target_id: str | ObjectId,
    target_type: str,
    reporter_id: int,
    reason: str = "flagged",
) -> bool:
    """Returns True if report was new, False if already reported by this user."""
    if isinstance(target_id, str):
        target_id = ObjectId(target_id)
    try:
        await _db().reports.insert_one({
            "target_id": target_id,
            "target_type": target_type,
            "reporter_id": reporter_id,
            "reason": reason,
            "resolved": False,
            "created_at": now_utc(),
        })
        return True
    except Exception:
        return False


async def get_pending_reports(limit: int = 20, skip: int = 0) -> list[dict]:
    cursor = _db().reports.find({"resolved": False}).sort("created_at", ASCENDING).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def count_reports_for_target(target_id: str | ObjectId, target_type: str) -> int:
    if isinstance(target_id, str):
        try:
            target_id = ObjectId(target_id)
        except Exception:
            return 0
    return await _db().reports.count_documents({"target_id": target_id, "target_type": target_type, "resolved": False})


async def resolve_report(report_id: str | ObjectId, admin_id: int, action: str) -> bool:
    if isinstance(report_id, str):
        report_id = ObjectId(report_id)
    res = await _db().reports.update_one(
        {"_id": report_id},
        {"$set": {"resolved": True, "resolved_by": admin_id, "action": action, "resolved_at": now_utc()}},
    )
    return res.modified_count > 0


async def resolve_reports_for_target(target_id: str | ObjectId, target_type: str, admin_id: int, action: str) -> int:
    if isinstance(target_id, str):
        try:
            target_id = ObjectId(target_id)
        except Exception:
            return 0
    res = await _db().reports.update_many(
        {"target_id": target_id, "target_type": target_type, "resolved": False},
        {"$set": {"resolved": True, "resolved_by": admin_id, "action": action, "resolved_at": now_utc()}},
    )
    return res.modified_count


async def log_admin_action(action: str, admin_id: int, details: dict | None = None) -> dict:
    doc = {
        "action": action,
        "admin_id": admin_id,
        "details": details or {},
        "created_at": now_utc(),
    }
    result = await _db().admin_logs.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


# ═════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═════════════════════════════════════════════════════════════════════════════

async def create_notification(recipient_id: int, payload: dict) -> dict:
    doc = {
        "recipient_id": recipient_id,
        "payload": payload,
        "read": False,
        "created_at": now_utc(),
    }
    result = await _db().notifications.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_unread_notifications(user_id: int, limit: int = 10) -> list[dict]:
    cursor = _db().notifications.find(
        {"recipient_id": user_id, "read": False}
    ).sort("created_at", DESCENDING).limit(limit)
    return await cursor.to_list(length=limit)


async def mark_notifications_read(user_id: int) -> int:
    res = await _db().notifications.update_many(
        {"recipient_id": user_id, "read": False},
        {"$set": {"read": True}},
    )
    return res.modified_count


# ═════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ═════════════════════════════════════════════════════════════════════════════

async def _track_event(event: str, meta: dict = None) -> None:
    """Fire-and-forget event tracking."""
    try:
        today = now_utc().date().isoformat()
        await _db().analytics.update_one(
            {"date": today, "event": event},
            {"$inc": {"count": 1}, "$set": {"meta": meta or {}}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("Analytics track error: %s", exc)


async def get_stats_snapshot() -> dict:
    db = _db()
    now = now_utc()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    approved_filter = {"is_deleted": False, "$or": [{"status": {"$exists": False}}, {"status": "approved"}]}
    pending_filter = {"is_deleted": False, "status": "pending"}
    total_questions = await db.questions.count_documents({"is_deleted": False})
    pending_questions = await db.questions.count_documents(pending_filter)
    approved_questions = await db.questions.count_documents(approved_filter)
    total_answers = await db.replies.count_documents({"is_deleted": False})
    total_reports = await db.reports.count_documents({"resolved": False})
    total_banned = await db.users.count_documents({"is_banned": True})
    total_muted = await db.users.count_documents({"is_muted": True})
    questions_today = await db.questions.count_documents({"is_deleted": False, "created_at": {"$gte": day_start}})
    answers_today = await db.replies.count_documents({"is_deleted": False, "created_at": {"$gte": day_start}})
    return {
        "total_users": await db.users.count_documents({}),
        "active_users_today": await db.users.count_documents({"last_active": {"$gte": day_start}}),
        "total_questions": total_questions,
        "pending_questions": pending_questions,
        "approved_questions": approved_questions,
        "total_answers": total_answers,
        "total_replies": total_answers,
        "pending_reports": total_reports,
        "banned_users": total_banned,
        "muted_users": total_muted,
        "questions_today": questions_today,
        "answers_today": answers_today,
    }


async def track_event(event: str, meta: dict = None) -> None:
    await _track_event(event, meta)
