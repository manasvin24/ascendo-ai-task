from __future__ import annotations

import logging
import re
from bs4 import BeautifulSoup

from ascendo_conf_agent.types import GraphState, CompanyRecord, Evidence
from ascendo_conf_agent.utils.urls import normalize_url

log = logging.getLogger(__name__)

# /UploadedFiles/EventPage/315401/images/Logos_0042_abb.jpg
LOGO_NAME_RE = re.compile(r"/Logos?\s*[_-]?\s*\d+\s*[_-]\s*([a-zA-Z0-9&\-\.\s]+)\.(?:png|jpg|jpeg|webp)", re.IGNORECASE)


def _clean_company_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name


def _extract_from_logos(url: str, html: str) -> list[CompanyRecord]:
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, CompanyRecord] = {}

    for img in soup.select("img"):
        src = img.get("src") or ""
        m = LOGO_NAME_RE.search(src)
        if not m:
            continue
        raw = m.group(1)
        name = _clean_company_name(raw.replace("_", " "))
        if not name:
            continue

        rec = out.get(name)
        if rec is None:
            rec = CompanyRecord(company_name=name)
            out[name] = rec
        rec.sources.add(url)
        rec.evidence.append(Evidence(url=url, snippet=f"Logo image src: {src}"))

    return list(out.values())


def _extract_from_speakers(url: str, html: str) -> tuple[list[CompanyRecord], int]:
    """
    Speakers page structure: inside each card:
      <p>Title<br><strong>Company</strong></p>
    We'll pull all <strong> tags under speaker blocks and count speakers.
    """
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, CompanyRecord] = {}

    speaker_cards = soup.select("div[class*='col-']") or soup.select("div")
    speaker_count = 0

    for card in speaker_cards:
        strongs = card.find_all("strong")
        if not strongs:
            continue

        # heuristic: the company is often the only strong in the card
        for st in strongs:
            company = _clean_company_name(st.get_text(" ", strip=True))
            if not company or len(company) < 2:
                continue
            speaker_count += 1

            rec = out.get(company)
            if rec is None:
                rec = CompanyRecord(company_name=company)
                out[company] = rec
            rec.sources.add(url)
            rec.speakers_count += 1
            rec.evidence.append(Evidence(url=url, snippet=f"Speakers page company: {company}"))

    return list(out.values()), speaker_count


def extractor_node(state: GraphState) -> GraphState:
    all_records: list[CompanyRecord] = []

    for rp in state.raw_pages:
        url = normalize_url(rp.url)

        # Root page contains the big logo grid: treat as logos-capable ALWAYS
        if rp.page_type in {"root", "logos"}:
            recs = _extract_from_logos(url, rp.html)
            if recs:
                log.info(f"Extracted {len(recs)} companies from {url}")
                all_records.extend(recs)

        if rp.page_type == "speakers" or url.rstrip("/").endswith("/speakers"):
            recs, _ = _extract_from_speakers(url, rp.html)
            if recs:
                # speakers extraction returns both companies and speaker counts per company
                log.info(f"Extracted {len(recs)} companies from {url}")
                log.info(f"Extracted {sum(r.speakers_count for r in recs)} speakers from {url}")
                all_records.extend(recs)

        # We do NOT call LLM here. Extraction is deterministic only.

    state.company_records = all_records
    return state
