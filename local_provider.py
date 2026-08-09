"""Local MLX provider — offline-capable LLM for simple chat.

Wraps ``mlx-lm`` with a lazy-loaded Phi-3-mini-4k model (~2.5GB in 4-bit).
Used by brain.py's hybrid router for ``intent == "chat"`` requests with
complexity <= 4, so simple conversations work without internet or cloud
credits. Returns "" on any failure so callers fall through to cloud.

Env vars:
    JARVIS_LOCAL_ENABLED   (default "1") — "0" disables the provider
    JARVIS_LOCAL_MODEL     (default "mlx-community/Phi-3-mini-4k-instruct-4bit")
    JARVIS_LOCAL_MAX_TOKENS (default "256")
"""
import os
import re
import threading

JARVIS_LOCAL_ENABLED = os.getenv("JARVIS_LOCAL_ENABLED", "1") == "1"
JARVIS_LOCAL_MODEL = os.getenv(
    "JARVIS_LOCAL_MODEL", "mlx-community/Phi-3-mini-4k-instruct-4bit"
)
JARVIS_LOCAL_MAX_TOKENS = int(os.getenv("JARVIS_LOCAL_MAX_TOKENS", "256"))

_model = None  # (model, tokenizer) tuple, or False once load has failed
_model_lock = threading.Lock()


def _load_model():
    global _model
    with _model_lock:
        if _model is not None:
            return _model if _model is not False else None
        try:
            from mlx_lm import load  # noqa: F401
        except ImportError as e:
            print(f"  Local provider: mlx-lm not installed ({e})")
            print("  Install with: pip install mlx-lm")
            _model = False
            return None
        try:
            print(f"  Loading local model {JARVIS_LOCAL_MODEL}...")
            model, tokenizer = load(JARVIS_LOCAL_MODEL)
            _model = (model, tokenizer)
            print("  Local provider ready (MLX)")
        except Exception as e:
            print(f"  Local model load failed: {e}")
            _model = False
        return _model if _model is not False else None


def is_available() -> bool:
    """True if the provider is enabled and the model is loadable."""
    if not JARVIS_LOCAL_ENABLED:
        return False
    return _load_model() is not None


def ask_local(prompt: str) -> str:
    """Single-turn chat with the local MLX model. Returns "" on any failure."""
    loaded = _load_model()
    if not loaded:
        return ""
    model, tokenizer = loaded
    try:
        import mlx_lm

        messages = [{"role": "user", "content": prompt}]
        try:
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            text = prompt
        out = mlx_lm.generate(
            model,
            tokenizer,
            prompt=text,
            max_tokens=JARVIS_LOCAL_MAX_TOKENS,
            verbose=False,
        )
        return _clean_output(out)
    except Exception as e:
        print(f"  Local provider error: {e}")
        return ""
    finally:
        try:
            import mlx.core as mx

            mx.clear_cache()
        except Exception:
            pass


def _clean_output(out: str) -> str:
    """Strip EOS/special tokens and stray whitespace from model output."""
    text = re.sub(r"<\|end\|>|<\|eot_id\|>|<\|user\|>|<\|assistant\|>", "", out)
    return text.strip()


def unload() -> None:
    """Drop the loaded model to free ~2.5GB RAM."""
    global _model
    with _model_lock:
        _model = None
