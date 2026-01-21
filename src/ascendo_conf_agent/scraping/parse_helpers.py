from __future__ import annotations
from bs4 import BeautifulSoup
from ascendo_conf_agent.utils.text import compact


def soupify(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def extract_text_snippet(el, max_len: int = 180) -> str | None:
    if el is None:
        return None
    txt = el.get_text(" ", strip=True) if hasattr(el, "get_text") else ""
    txt = compact(txt, max_len=max_len)
    return txt or None
