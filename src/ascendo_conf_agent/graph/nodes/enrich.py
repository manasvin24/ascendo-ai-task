from __future__ import annotations

import re
from ascendo_conf_agent.types import GraphState

SIGNALS = [
    "field service", "fsm", "dispatch", "technician", "workforce", "maintenance",
    "asset", "spares", "parts", "inventory", "service operations", "service ops",
    "customer service", "technical support", "service", "services",
    "sap", "ifs", "servicenow", "oracle field service", "salesforce service",
]


SEGMENTS = [
    ("FSM Platform", ["fsm", "field service management", "servicenow", "ifs", "oracle field service", "sap"]),
    ("Spares/Parts", ["spares", "parts", "inventory"]),
    ("Field Service Operator", ["utilities", "telecom", "hvac", "maintenance", "technician", "dispatch"]),
    ("Partner/SI", ["consulting", "systems integrator", "implementation", "partner"]),
]


def enrich_node(state: GraphState) -> GraphState:
    for rec in state.company_records:
        blob = " ".join(rec.speaker_titles + rec.session_titles + [e.snippet or "" for e in rec.evidence])
        blob_l = blob.lower()

        hits = []
        for s in SIGNALS:
            if s in blob_l:
                hits.append(s)
        rec.signals = sorted(set(hits))

        # segment guess (best-effort)
        segment = "Unclear"
        for seg, keys in SEGMENTS:
            if any(k in blob_l for k in keys):
                segment = seg
                break
        rec.hinted_segment = segment

    return state
