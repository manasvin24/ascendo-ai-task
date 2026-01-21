from __future__ import annotations

import logging
import os
import pandas as pd

from ascendo_conf_agent.config import SETTINGS
from ascendo_conf_agent.types import GraphState

log = logging.getLogger(__name__)


def export_node(state: GraphState) -> GraphState:
    os.makedirs(SETTINGS.output_dir, exist_ok=True)

    fit_map = {r.company_name: r for r in state.fit_results}
    rows = []
    for rec in state.company_records:
        fr = fit_map.get(rec.company_name)
        rows.append(
            {
                "company_name": rec.company_name,
                "icp_fit": fr.icp_fit if fr else "",
                "confidence": fr.confidence if fr else "",
                "rationale": fr.rationale if fr else "",
                "speakers_count": rec.speakers_count,
                "sources": "; ".join(sorted(rec.sources))[:3000],
                "evidence_sample": " | ".join([e.snippet for e in rec.evidence[:3]])[:3000],
            }
        )

    df = pd.DataFrame(rows).sort_values(["icp_fit", "company_name"], ascending=[True, True])

    slug = "fieldserviceusa"
    out_path = os.path.join(SETTINGS.output_dir, f"{slug}_companies.xlsx")
    df.to_excel(out_path, index=False)

    state.notes["output_path"] = out_path
    log.info(f"Output: {out_path}")
    return state
