"""Memoriq embedder — generates vector embeddings using fastembed.

Lazy-loads the model on first use. Caches the singleton instance.
Uses BAAI/bge-small-en-v1.5 (384 dimensions, ~50MB, CPU-only via ONNX).
"""

import struct
import os
import time as _time
from pathlib import Path
from typing import Optional
from datetime import datetime as _dt

# Suppress symlink warning on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
CACHE_DIR = str(Path.home() / ".memoriq" / "cache" / "embeddings")

_model = None
_TRACE_FILE = Path.home() / ".memoriq" / "logs" / "trace.log"


def _trace(msg):
    """Unbuffered trace logging for debugging hangs."""
    try:
        with open(_TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(f"{_dt.now().isoformat()} [embedder] {msg}\n")
    except Exception:
        pass


def _get_model():
    """Lazy-load the embedding model (singleton)."""
    global _model
    if _model is not None:
        return _model
    _trace("_get_model: loading (first call)")
    t0 = _time.time()
    _trace("_get_model: importing fastembed.TextEmbedding...")
    from fastembed import TextEmbedding
    _trace(f"_get_model: import done in {_time.time()-t0:.2f}s, creating model...")
    _model = TextEmbedding(EMBEDDING_MODEL, cache_dir=CACHE_DIR)
    _trace(f"_get_model: model created in {_time.time()-t0:.2f}s total")
    return _model


def embed_text(text: str) -> bytes:
    """Generate embedding for a single text string. Returns raw bytes for sqlite-vec."""
    t0 = _time.time()
    _trace(f"embed_text: start (text={text[:30]!r})")
    model = _get_model()
    _trace(f"embed_text: model ready in {_time.time()-t0:.3f}s, embedding...")
    embeddings = list(model.embed([text]))
    vector = embeddings[0]
    result = struct.pack(f"<{EMBEDDING_DIM}f", *vector)
    _trace(f"embed_text: done in {_time.time()-t0:.3f}s")
    return result


def embed_texts(texts: list[str]) -> list[bytes]:
    """Generate embeddings for multiple texts. Returns list of raw bytes."""
    if not texts:
        return []
    model = _get_model()
    embeddings = list(model.embed(texts))
    results = []
    for vector in embeddings:
        results.append(struct.pack(f"<{EMBEDDING_DIM}f", *vector))
    return results


def is_available() -> bool:
    """Check if fastembed is installed."""
    try:
        import fastembed  # noqa: F401
        return True
    except ImportError:
        return False


def unload_model():
    """Unload the embedding model to free memory.

    Useful in memory-constrained environments. Model will be
    reloaded on next embed_text() call.
    """
    global _model
    if _model is not None:
        _trace("unload_model: unloading model")
        _model = None


def preload_model() -> bool:
    """Eagerly preload the embedding model.

    Returns True if model loaded successfully, False otherwise.
    """
    try:
        _get_model()
        return True
    except Exception:
        return False


def get_model_memory_usage() -> dict:
    """Get memory usage statistics for the embedding model.

    Returns dict with:
        - loaded: bool - whether model is currently loaded
        - model_size_mb: estimated model size in MB
        - cache_dir: path to embedding cache directory
    """
    global _model
    return {
        "loaded": _model is not None,
        "model_size_mb": 50,  # BAAI/bge-small-en-v1.5 is ~50MB
        "cache_dir": CACHE_DIR,
    }
