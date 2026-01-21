from __future__ import annotations

import asyncio
from playwright.async_api import async_playwright
from rich.logging import RichHandler
import logging

from ascendo_conf_agent.config import SETTINGS

log = logging.getLogger(__name__)


async def fetch_html(url: str, headless: bool = True) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(user_agent=SETTINGS.user_agent)
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=SETTINGS.nav_timeout_ms)
        # let client JS render
        await page.wait_for_timeout(SETTINGS.wait_after_load_ms)

        # scroll a bit (logos sometimes lazy-load)
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(600)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(300)
        except Exception:
            pass

        html = await page.content()
        await context.close()
        await browser.close()
        return html


def fetch_html_sync(url: str, headless: bool = True) -> str:
    return asyncio.run(fetch_html(url, headless=headless))
