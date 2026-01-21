from __future__ import annotations

import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    # Gemini
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-lite")

    # scraping
    user_agent: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    )
    nav_timeout_ms: int = int(os.getenv("NAV_TIMEOUT_MS", "45000"))
    wait_after_load_ms: int = int(os.getenv("WAIT_AFTER_LOAD_MS", "1200"))

    # LLM throttling (free tier safe)
    gemini_min_interval_s: float = float(os.getenv("GEMINI_MIN_INTERVAL_S", "3.0"))
    gemini_max_attempts: int = int(os.getenv("GEMINI_MAX_ATTEMPTS", "3"))

    # output
    output_dir: str = os.getenv("OUTPUT_DIR", "outputs")


SETTINGS = Settings()
