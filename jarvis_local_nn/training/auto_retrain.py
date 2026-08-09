"""Debounced background auto-retrain for the local intent router.

Triggered when the learner writes a new tool (see brain._on_tool_learned).
Runs in a daemon thread so the main loop is never blocked. Debounces to at
most one retrain per JARVIS_AUTO_RETRAIN_INTERVAL seconds. After a successful
retrain the weights are exported and the in-memory router cache is dropped so
the next predict uses the fresh model.

Disable with JARVIS_AUTO_RETRAIN_ENABLED=0.
"""

import os
import threading
import time

AUTO_RETRAIN_ENABLED = os.getenv("JARVIS_AUTO_RETRAIN_ENABLED", "1") == "1"
RETRAIN_MIN_INTERVAL = float(os.getenv("JARVIS_AUTO_RETRAIN_INTERVAL", "600"))

_lock = threading.Lock()
_pending = False
_running = False
_last_run = 0.0


def schedule_retrain() -> None:
    """Debounced: request a background retrain. No-op when disabled or too soon."""
    if not AUTO_RETRAIN_ENABLED:
        return
    global _pending, _running, _last_run
    with _lock:
        now = time.time()
        if _running or now - _last_run < RETRAIN_MIN_INTERVAL:
            _pending = True
            return
        _running = True
    threading.Thread(target=_retrain_worker, name="jarvis-auto-retrain", daemon=True).start()


def _retrain_worker() -> None:
    global _pending, _running, _last_run
    try:
        from ..models.router import export_weights
        from .train import WEIGHTS_PATH, train

        result = train(synth_per_class=50, epochs=30, verbose=False, include_learned=True)
        export_weights(result["mlp"], WEIGHTS_PATH)
        from ..integration.local_router import reload_router

        reload_router()
        _last_run = time.time()
        print(
            f"[Auto-retrain] Router retrained: val_acc={result['val_acc']:.3f} "
            f"({result['n_train']} train / {result['n_val']} val)"
        )
    except Exception as e:
        print(f"[Auto-retrain] Failed: {e}")
    finally:
        with _lock:
            _running = False
            if _pending:
                _pending = False
                _last_run = 0.0
