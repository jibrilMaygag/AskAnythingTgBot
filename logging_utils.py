import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def setup_logging() -> None:
    log_file = Path(__file__).resolve().parent / "bot.log"
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


def log_event(event: str, user_id: int | None = None, details: dict[str, Any] | None = None) -> None:
    logger = logging.getLogger("bot")
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "details": details or {},
    }
    logger.info(json.dumps(payload, default=str, ensure_ascii=False))
