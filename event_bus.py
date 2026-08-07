import os
import time
import threading
import json
from collections import deque
from typing import Callable, Dict, List

# Configuration (environment overrides)
_MAX_EVENTS = int(os.getenv("JARVIS_EVENT_RETENTION", "1000"))  # max per event type
_TTL_SECONDS = int(os.getenv("JARVIS_EVENT_TTL_HOURS", "24")) * 3600  # retain events for 24h by default

_lock = threading.RLock()
_subscribers: Dict[str, List[Callable[[dict], None]]] = {}
_recent: Dict[str, deque] = {}

def _cleanup() -> None:
    """Remove stale events older than TTL."""
    now = time.time()
    cutoff = now - _TTL_SECONDS
    with _lock:
        for etype, dq in list(_recent.items()):
            while dq and dq[0][0] < cutoff:
                dq.popleft()
            if not dq:
                _recent.pop(etype, None)

def publish(event_type: str, payload: dict) -> None:
    """Publish an event.

    The payload is stored in the recent events buffer (with a timestamp) and all
    registered callbacks for the event_type are invoked in separate daemon threads.
    """
    _cleanup()
    ts = time.time()
    with _lock:
        dq = _recent.setdefault(event_type, deque(maxlen=_MAX_EVENTS))
        dq.append((ts, payload))
        # Snapshot callbacks to avoid race conditions during iteration
        callbacks = list(_subscribers.get(event_type, []))
    for cb in callbacks:
        # Invoke callbacks asynchronously to keep publish fast
        threading.Thread(target=cb, args=(payload,), daemon=True).start()

def subscribe(event_type: str, callback: Callable[[dict], None]) -> None:
    """Register a callback for a specific event_type.

    Callbacks receive the payload dictionary (no timestamp). They should be
    lightweight; heavy work can be off‑loaded to a separate thread if needed.
    """
    with _lock:
        _subscribers.setdefault(event_type, []).append(callback)

def get_recent(event_type: str, limit: int = 50) -> List[dict]:
    """Return the most recent *limit* payloads for *event_type* (newest last)."""
    with _lock:
        dq = _recent.get(event_type, deque())
        # Slice only the payloads, drop timestamps
        return [payload for _, payload in list(dq)[-limit:]]

def get_all_recent(limit_per_type: int = 20) -> Dict[str, List[dict]]:
    """Return a mapping of event_type → recent payload list for every stored type."""
    with _lock:
        return {etype: [payload for _, payload in list(dq)[-limit_per_type:]] for etype, dq in _recent.items()}
