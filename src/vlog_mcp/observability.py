from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator


logger = logging.getLogger("vlog_mcp")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, "ts": time.time(), **fields}
    logger.info(json.dumps(payload, ensure_ascii=False))


@contextmanager
def traced(operation: str, **fields: Any) -> Iterator[None]:
    start = time.time()
    log_event(f"{operation}.start", **fields)
    try:
        yield
        log_event(f"{operation}.ok", duration_ms=int((time.time() - start) * 1000), **fields)
    except Exception as exc:
        log_event(f"{operation}.error", duration_ms=int((time.time() - start) * 1000), error=str(exc), **fields)
        raise
