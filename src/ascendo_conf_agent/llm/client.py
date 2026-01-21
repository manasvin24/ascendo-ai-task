from __future__ import annotations

import json
import os
import re
import time
import random
import logging
from collections import deque
from threading import Lock
from typing import Any, Optional

from ascendo_conf_agent.config import SETTINGS

log = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

_LOCK = Lock()
_NEXT_ALLOWED_TS = 0.0
# Rolling window tracker for 15 RPM (requests per minute)
_CALL_HISTORY: deque = deque(maxlen=100)  # Track last 100 calls
_RPM_LIMIT = 15
_WINDOW_SECONDS = 60.0


def load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_balanced_json_object(text: str) -> str | None:
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _parse_retry_delay_seconds(err_msg: str) -> int | None:
    m = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", err_msg, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(float(m.group(1)) + 1.0)
    except Exception:
        return None


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or SETTINGS.gemini_api_key
        self.model = model or SETTINGS.gemini_model

        if not self.api_key:
            raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_API_KEY).")
        if not self.model:
            raise RuntimeError("Set GEMINI_MODEL to a valid model name.")

        from google import genai  # type: ignore

        self._client = genai.Client(api_key=self.api_key)
        self.min_interval_s = SETTINGS.gemini_min_interval_s
        self.max_attempts = SETTINGS.gemini_max_attempts

    def _acquire_slot(self) -> None:
        """
        Enforce both:
        1. Minimum interval between calls (simple throttle)
        2. Rolling 60s window with 15 RPM limit
        """
        global _NEXT_ALLOWED_TS, _CALL_HISTORY
        with _LOCK:
            now = time.monotonic()
            
            # Clean old calls outside 60s window
            cutoff = now - _WINDOW_SECONDS
            while _CALL_HISTORY and _CALL_HISTORY[0] < cutoff:
                _CALL_HISTORY.popleft()
            
            # Check if we're at RPM limit
            if len(_CALL_HISTORY) >= _RPM_LIMIT:
                # Calculate time until oldest call expires from window
                oldest_call = _CALL_HISTORY[0]
                wait_until = oldest_call + _WINDOW_SECONDS
                if wait_until > now:
                    wait_time = wait_until - now
                    log.info(f"Rate limit: {len(_CALL_HISTORY)}/{_RPM_LIMIT} calls in window. Waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                    now = time.monotonic()
                    # Clean again after sleep
                    cutoff = now - _WINDOW_SECONDS
                    while _CALL_HISTORY and _CALL_HISTORY[0] < cutoff:
                        _CALL_HISTORY.popleft()
            
            # Enforce minimum interval
            if now < _NEXT_ALLOWED_TS:
                time.sleep(_NEXT_ALLOWED_TS - now)
                now = time.monotonic()
            
            # Record this call and set next allowed time
            _CALL_HISTORY.append(now)
            _NEXT_ALLOWED_TS = now + self.min_interval_s + random.uniform(0.05, 0.25)

    def _acquire_slot(self) -> None:
        global _NEXT_ALLOWED_TS
        with _LOCK:
            now = time.monotonic()
            if now < _NEXT_ALLOWED_TS:
                time.sleep(_NEXT_ALLOWED_TS - now)
            _NEXT_ALLOWED_TS = time.monotonic() + self.min_interval_s + random.uniform(0.05, 0.25)

    def _extract_json_text(self, raw: str) -> str:
        raw = (raw or "").strip()
        if not raw:
            return "{}"
        if raw.startswith("{") and raw.endswith("}"):
            return raw
        m = _JSON_FENCE_RE.search(raw)
        if m:
            return m.group(1).strip()
        cand = _extract_balanced_json_object(raw)
        if cand:
            return cand.strip()
        return "{}"

    def json_chat(self, system: str, user: str, max_tokens: int = 1200) -> dict[str, Any]:
        prompt = (
            f"{system}\n\n"
            f"USER_INPUT:\n{user}\n\n"
            f"IMPORTANT: Return ONLY valid JSON. No markdown, no commentary."
        )

        last_err: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._acquire_slot()
            try:
                resp = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={"temperature": 0.2, "max_output_tokens": max_tokens},
                )
                raw = getattr(resp, "text", "") or ""
                return json.loads(self._extract_json_text(raw))
            except Exception as e:
                last_err = e
                err_str = str(e)
                
                # Check if it's a 429 rate limit error
                is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()
                
                if is_429:
                    # Parse server-suggested retry delay
                    delay = _parse_retry_delay_seconds(err_str)
                    if delay is None:
                        # Default exponential backoff for 429
                        delay = min(60, 5 * (2 ** (attempt - 1)))
                    log.warning(f"429 rate limit hit on attempt {attempt}/{self.max_attempts}. Waiting {delay}s before retry.")
                    time.sleep(delay)
                    continue
                
                # For other errors, use exponential backoff
                backoff = min(45, 2 ** min(attempt, 6) + random.uniform(0.1, 0.8))
                log.warning(f"API error on attempt {attempt}/{self.max_attempts}: {err_str[:100]}. Retrying in {backoff:.1f}s")
                time.sleep(backoff)

        raise RuntimeError(f"Gemini failed after {self.max_attempts} attempts: {last_err}") from last_err
