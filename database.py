import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
REPLIES_FILE = os.path.join(DATA_DIR, "replies.json")
VOTES_FILE = os.path.join(DATA_DIR, "votes.json")
REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")
VIEW_OFFSETS_FILE = os.path.join(DATA_DIR, "view_offsets.json")


def ensure_data_dir():
    """Ensure data directory exists."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def load_json(filepath: str, default: Dict = None) -> Dict:
    """Load JSON file, return default if not exists."""
    if default is None:
        default = {}
    ensure_data_dir()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except:
            return default
    return default


def save_json(filepath: str, data: Dict):
    """Save data to JSON file."""
    ensure_data_dir()
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


# ============= USERS =============
def get_user(user_id: int) -> Optional[Dict]:
    """Get user by ID."""
    users = load_json(USERS_FILE)
    return users.get(str(user_id))


def create_user(user_id: int, username: str = None) -> Dict:
    """Create new user."""
    users = load_json(USERS_FILE)
    if str(user_id) in users:
        return users[str(user_id)]
    
    user = {
        "id": user_id,
        "username": username,
        "display_name": None,
        "gender": None,  # "M", "F", or None
        "created_at": datetime.now().isoformat(),
        "total_questions": 0,
        "total_replies": 0,
    }
    users[str(user_id)] = user
    save_json(USERS_FILE, users)
    return user


def update_user(user_id: int, **kwargs) -> Dict:
    """Update user fields."""
    users = load_json(USERS_FILE)
    user_id_str = str(user_id)
    if user_id_str not in users:
        return create_user(user_id)
    
    users[user_id_str].update(kwargs)
    save_json(USERS_FILE, users)
    return users[user_id_str]


def set_user_profile(user_id: int, display_name: str, gender: Optional[str] = None) -> Dict:
    """Set user display name and gender."""
    return update_user(user_id, display_name=display_name, gender=gender)


# ============= QUESTIONS =============
def create_question(user_id: int, topic: str, text: str) -> Dict:
    """Create new question."""
    questions = load_json(QUESTIONS_FILE)
    question_id = uuid.uuid4().hex[:8]
    
    question = {
        "id": question_id,
        "user_id": user_id,
        "topic": topic,
        "text": text,
        "created_at": datetime.now().isoformat(),
        "message_id": None,  # Will be set after sending to channel
        "chat_id": None,
        "reply_count": 0,
    }
    questions[question_id] = question
    save_json(QUESTIONS_FILE, questions)
    
    # Update user stats
    user = get_user(user_id)
    if user:
        question_ids = user.get("question_ids", [])
        question_ids.append(question_id)
        update_user(user_id, 
                   total_questions=user["total_questions"] + 1,
                   question_ids=question_ids)
    
    return question


def get_question(question_id: str) -> Optional[Dict]:
    """Get question by ID."""
    questions = load_json(QUESTIONS_FILE)
    return questions.get(question_id)


def update_question(question_id: str, **kwargs) -> Dict:
    """Update question fields."""
    questions = load_json(QUESTIONS_FILE)
    if question_id not in questions:
        return None
    
    questions[question_id].update(kwargs)
    save_json(QUESTIONS_FILE, questions)
    return questions[question_id]


def get_all_questions() -> List[Dict]:
    """Get all questions sorted by newest first."""
    questions = load_json(QUESTIONS_FILE)
    return sorted(questions.values(), key=lambda x: x["created_at"], reverse=True)


# ============= REPLIES =============
def create_reply(question_id: str, user_id: int, text: str, parent_reply_id: Optional[str] = None) -> Dict:
    """Create new reply to a question."""
    replies = load_json(REPLIES_FILE)
    reply_id = uuid.uuid4().hex[:8]
    
    reply = {
        "id": reply_id,
        "question_id": question_id,
        "user_id": user_id,
        "text": text,
        "parent_reply_id": parent_reply_id,  # For nested replies
        "created_at": datetime.now().isoformat(),
        "message_id": None,  # Will be set after sending
        "chat_id": None,
        "upvotes": 0,
        "downvotes": 0,
    }
    replies[reply_id] = reply
    save_json(REPLIES_FILE, replies)
    
    # Update question reply count
    question = get_question(question_id)
    if question:
        update_question(question_id, reply_count=question["reply_count"] + 1)
    
    # Increment user reply count
    update_user(user_id, total_replies=get_user(user_id)["total_replies"] + 1)
    
    return reply


def get_reply(reply_id: str) -> Optional[Dict]:
    """Get reply by ID."""
    replies = load_json(REPLIES_FILE)
    return replies.get(reply_id)


def get_replies_for_question(question_id: str) -> List[Dict]:
    """Get all replies for a question, sorted by newest first."""
    replies = load_json(REPLIES_FILE)
    question_replies = [r for r in replies.values() if r["question_id"] == question_id]
    return sorted(question_replies, key=lambda x: x["created_at"], reverse=True)


def update_reply(reply_id: str, **kwargs) -> Optional[Dict]:
    """Update reply fields."""
    replies = load_json(REPLIES_FILE)
    if reply_id not in replies:
        return None
    
    replies[reply_id].update(kwargs)
    save_json(REPLIES_FILE, replies)
    return replies[reply_id]


# ============= VOTES =============
def add_vote(reply_id: str, user_id: int, vote_type: str) -> bool:
    """Add a vote (up/down). Returns True if added, False if already voted."""
    votes = load_json(VOTES_FILE)
    if reply_id not in votes:
        votes[reply_id] = {}
    
    reply_votes = votes[reply_id]
    user_id_str = str(user_id)
    
    # Check if user already voted
    for vote_type_key, voters in reply_votes.items():
        if user_id_str in voters:
            # Already voted
            return False
    
    # Remove old vote if changing vote
    if user_id_str in reply_votes.get("up", []):
        reply_votes["up"].remove(user_id_str)
    if user_id_str in reply_votes.get("down", []):
        reply_votes["down"].remove(user_id_str)
    
    # Add new vote
    if vote_type not in reply_votes:
        reply_votes[vote_type] = []
    reply_votes[vote_type].append(user_id_str)
    
    save_json(VOTES_FILE, votes)
    
    # Update reply counts
    reply = get_reply(reply_id)
    if reply:
        upvotes = len(reply_votes.get("up", []))
        downvotes = len(reply_votes.get("down", []))
        update_reply(reply_id, upvotes=upvotes, downvotes=downvotes)
    
    return True


def get_user_vote(reply_id: str, user_id: int) -> Optional[str]:
    """Get user's vote on a reply ('up', 'down', or None)."""
    votes = load_json(VOTES_FILE)
    reply_votes = votes.get(reply_id, {})
    user_id_str = str(user_id)
    
    if user_id_str in reply_votes.get("up", []):
        return "up"
    if user_id_str in reply_votes.get("down", []):
        return "down"
    return None


def change_vote(reply_id: str, user_id: int, new_vote: str) -> bool:
    """Change a user's vote. Returns True if successful."""
    votes = load_json(VOTES_FILE)
    if reply_id not in votes:
        votes[reply_id] = {}
    
    reply_votes = votes[reply_id]
    user_id_str = str(user_id)
    
    # Remove old vote
    for vote_type_key in ["up", "down"]:
        if vote_type_key in reply_votes and user_id_str in reply_votes[vote_type_key]:
            reply_votes[vote_type_key].remove(user_id_str)
    
    # Add new vote
    if new_vote not in reply_votes:
        reply_votes[new_vote] = []
    reply_votes[new_vote].append(user_id_str)
    
    save_json(VOTES_FILE, votes)
    
    # Update reply counts
    reply = get_reply(reply_id)
    if reply:
        upvotes = len(reply_votes.get("up", []))
        downvotes = len(reply_votes.get("down", []))
        update_reply(reply_id, upvotes=upvotes, downvotes=downvotes)
    
    return True


# ============= REPORTS =============
def add_report(reply_id: str, user_id: int) -> bool:
    """Report a reply. Returns True if reported, False if already reported by user."""
    reports = load_json(REPORTS_FILE)
    if reply_id not in reports:
        reports[reply_id] = []
    
    user_id_str = str(user_id)
    if user_id_str not in reports[reply_id]:
        reports[reply_id].append(user_id_str)
        save_json(REPORTS_FILE, reports)
        return True
    return False


def get_reports_for_reply(reply_id: str) -> List[int]:
    """Get list of user IDs who reported a reply."""
    reports = load_json(REPORTS_FILE)
    reporter_ids = reports.get(reply_id, [])
    return [int(uid) for uid in reporter_ids]


# ============= VIEW OFFSETS =============
def set_view_offset(user_id: int, question_id: str, offset: int):
    """Set how many replies a user has seen for a question."""
    offsets = load_json(VIEW_OFFSETS_FILE)
    user_id_str = str(user_id)
    
    if user_id_str not in offsets:
        offsets[user_id_str] = {}
    
    offsets[user_id_str][question_id] = offset
    save_json(VIEW_OFFSETS_FILE, offsets)


def get_view_offset(user_id: int, question_id: str) -> int:
    """Get how many replies a user has seen for a question."""
    offsets = load_json(VIEW_OFFSETS_FILE)
    return offsets.get(str(user_id), {}).get(question_id, 0)
