from __future__ import annotations
import re

_SUFFIXES = [
    r"\binc\b", r"\binc\.\b", r"\bllc\b", r"\bltd\b", r"\bltd\.\b",
    r"\bcorp\b", r"\bcorp\.\b", r"\bcorporation\b", r"\bco\b", r"\bco\.\b",
    r"\bplc\b", r"\bgmbh\b", r"\bag\b", r"\bsa\b",
]

_SUFFIX_RE = re.compile(r"(" + "|".join(_SUFFIXES) + r")", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s&-]")


def normalize_company_name(name: str) -> str:
    n = name.strip()
    n = _PUNCT_RE.sub(" ", n)
    n = _SUFFIX_RE.sub(" ", n)
    n = _WS_RE.sub(" ", n).strip().lower()
    return n


def compact(s: str, max_len: int = 180) -> str:
    s = _WS_RE.sub(" ", s.strip())
    return s if len(s) <= max_len else s[: max_len - 3] + "..."
