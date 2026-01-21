from __future__ import annotations

import logging
import re

from ascendo_conf_agent.types import GraphState, CompanyRecord, Evidence

log = logging.getLogger(__name__)


def _norm_key(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^\w\s&\-\.]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def normalizer_node(state: GraphState) -> GraphState:
    merged: dict[str, CompanyRecord] = {}

    for rec in state.company_records:
        key = _norm_key(rec.company_name)
        if not key:
            continue
        if key not in merged:
            merged[key] = CompanyRecord(company_name=rec.company_name)
        tgt = merged[key]
        tgt.sources |= rec.sources
        tgt.speakers_count += rec.speakers_count
        tgt.evidence.extend(rec.evidence)

    state.company_records = list(merged.values())
    log.info(f"Normalized into {len(state.company_records)} unique company records")
    return state
