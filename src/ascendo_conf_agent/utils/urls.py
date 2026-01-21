from __future__ import annotations

from urllib.parse import urljoin, urlparse


def absolutize(base: str, maybe_relative: str) -> str:
    return urljoin(base, maybe_relative)


def normalize_url(u: str) -> str:
    p = urlparse(u)
    # normalize: remove fragment, keep trailing slash consistent
    out = p._replace(fragment="").geturl()
    return out
