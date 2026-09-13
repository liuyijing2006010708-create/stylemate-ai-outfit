"""Per-operation trace identifiers with only safe, fixed log fields.

Logs carry request id, stage, model, protocol, HTTP status and duration —
never API keys, image bytes, URLs or provider response content.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("stylemate.requests")
# INFO 事件必须真实输出：默认 root logger 只发 WARNING，这里补自己的 handler。
if logger.level == logging.NOTSET:
    logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)

SAFE_FIELDS = {"model", "protocol", "status", "retries", "http", "duration_ms"}


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def _details(fields: dict[str, Any]) -> str:
    return " ".join(
        f"{name}={' '.join(str(value).split())[:200]}" for name, value in fields.items()
        if name in SAFE_FIELDS
        and isinstance(value, (str, int, float)) and value != ""
    )


@contextmanager
def trace(request_id: str, stage: str, *, model: str = "", protocol: str = "", **fields):
    details = _details({"model": model, "protocol": protocol, **fields})
    started = time.monotonic()
    logger.info("req=%s stage=%s event=start %s", request_id, stage, details)
    try:
        yield request_id
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        logger.warning(
            "req=%s stage=%s event=failed http=%s duration_ms=%d %s",
            request_id, stage, status if isinstance(status, int) else "",
            (time.monotonic() - started) * 1000, details,
        )
        raise
    logger.info(
        "req=%s stage=%s event=done duration_ms=%d %s",
        request_id, stage, (time.monotonic() - started) * 1000, details,
    )


def log_event(request_id: str, stage: str, event: str, **fields) -> None:
    logger.info("req=%s stage=%s event=%s %s", request_id, stage, event, _details(fields))
