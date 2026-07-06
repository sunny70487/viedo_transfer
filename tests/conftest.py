import sys
import types
from unittest.mock import MagicMock


def _register_stub(name: str, attrs: dict | None = None) -> None:
    """Register a stub top-level module when the real dep is not installed.

    CI runs with a minimal dependency set (see .github/workflows/ci.yml).
    Backend code performs top-level `import torch` / `from openai import OpenAI`,
    which would otherwise fail at collection time.  Tests that exercise real
    behaviour patch these symbols explicitly, so a plain stub is enough.
    """
    if name in sys.modules:
        return
    module = types.ModuleType(name)
    for key, value in (attrs or {}).items():
        setattr(module, key, value)
    sys.modules[name] = module


try:
    import torch  # noqa: F401
except ImportError:
    _register_stub("torch", {"cuda": MagicMock()})

try:
    import openai  # noqa: F401
except ImportError:
    _register_stub("openai", {"OpenAI": MagicMock()})

try:
    import yt_dlp  # noqa: F401
except ImportError:
    _register_stub("yt_dlp", {
        "YoutubeDL": MagicMock(),
        "utils": types.SimpleNamespace(DownloadError=Exception),
    })

try:
    import pydub  # noqa: F401
except ImportError:
    _register_stub("pydub", {"AudioSegment": MagicMock()})

try:
    import funasr  # noqa: F401
except ImportError:
    _register_stub("funasr", {"AutoModel": MagicMock()})

try:
    import faster_whisper  # noqa: F401
except ImportError:
    _register_stub("faster_whisper", {"WhisperModel": MagicMock()})

try:
    import dotenv  # noqa: F401
except ImportError:
    _register_stub("dotenv", {"load_dotenv": lambda *a, **kw: None})
