from __future__ import annotations

import logging
import re
import os
import pandas as pd
from datetime import datetime

from ascendo_conf_agent.types import GraphState, CompanyRecord, Evidence
from ascendo_conf_agent.config import SETTINGS

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
    
    # Write extraction artifact (CSV 1)
    _write_extraction_artifact(state)
    
    return state


def _write_extraction_artifact(state: GraphState) -> None:
    """Write extracted companies to CSV for reproducibility and agent handoff."""
    os.makedirs(SETTINGS.output_dir, exist_ok=True)
    
    rows = []
    for rec in state.company_records:
        evidence_urls = [e.url for e in rec.evidence]
        evidence_snippets = [e.snippet[:100] for e in rec.evidence[:3]]
        
        rows.append({
            "company_name": rec.company_name,
            "speakers_count": rec.speakers_count,
            "source_pages": "; ".join(sorted(rec.sources)),
            "evidence_urls": " | ".join(evidence_urls[:5]),
            "evidence_snippets": " | ".join(evidence_snippets),
            "extracted_at": datetime.now().isoformat(),
            "extraction_method": "playwright_html_parsing"
        })
    
    df = pd.DataFrame(rows)
    csv_path = os.path.join(SETTINGS.output_dir, "stage1_extracted_companies.csv")
    df.to_csv(csv_path, index=False)
    
    if not hasattr(state, "notes") or state.notes is None:
        state.notes = {}
    state.notes["extraction_artifact"] = csv_path
    
    log.info(f"ARTIFACT: Wrote {len(rows)} companies to {csv_path}")
