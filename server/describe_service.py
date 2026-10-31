"""Description parsing used by the upload endpoint. Offline rules now; T17 adds the optional Gemini call in front of them."""
from __future__ import annotations

from typing import Any

from core.profiles import describe


def parse(text: str) -> dict[str, Any]:
    return describe.parse_offline(text)
