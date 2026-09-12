import logging
from collections import deque
from datetime import datetime, timezone

_MAX_ENTRIES = 50
_recent_errors: deque[dict] = deque(maxlen=_MAX_ENTRIES)


class RingBufferHandler(logging.Handler):
    """Keeps the last N error/critical log records in memory for /health/errors.

    Intentionally shallow -- this is a peek for a dashboard, not a log store.
    No stack traces or request bodies, just level/timestamp/message.
    """

    def emit(self, record: logging.LogRecord) -> None:
        _recent_errors.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
            }
        )


def install() -> None:
    handler = RingBufferHandler(level=logging.ERROR)
    logging.getLogger().addHandler(handler)


def recent_errors() -> list[dict]:
    return list(_recent_errors)
