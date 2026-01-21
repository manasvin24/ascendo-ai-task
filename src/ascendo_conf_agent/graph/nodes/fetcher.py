from __future__ import annotations

import logging

from ascendo_conf_agent.types import GraphState, RawPage
from ascendo_conf_agent.scraping.playwright_fetch import fetch_html_sync

log = logging.getLogger(__name__)


def fetcher_node(state: GraphState) -> GraphState:
    raw_pages: list[RawPage] = []
    for t in state.targets:
        log.info(f"Fetching: {t.url}")
        html = fetch_html_sync(t.url, headless=state.headless)
        raw_pages.append(RawPage(url=t.url, page_type=t.page_type, html=html))

    state.raw_pages = raw_pages
    return state
