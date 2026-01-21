from __future__ import annotations

from collections import Counter
from ascendo_conf_agent.types import GraphState, QAFlag
from ascendo_conf_agent.utils.text import normalize_company_name


def qa_node(state: GraphState) -> GraphState:
    flags: list[QAFlag] = []

    norm_counts = Counter(normalize_company_name(r.company_name) for r in state.company_records)
    fit_map = {r.company_name: r for r in state.fit_results}

    for rec in state.company_records:
        f = []
        if not rec.company_name.strip():
            f.append("missing_company_name")
        if norm_counts[rec.normalized_name] > 1:
            f.append("possible_duplicate")
        # If we have speaker_count but fit says No, flag (could be extraction weirdness)
        fr = fit_map.get(rec.company_name)
        if fr and rec.speaker_count > 0 and fr.icp_fit == "No":
            f.append("has_speakers_but_fit_no")

        if f:
            flags.append(QAFlag(company_name=rec.company_name, flags=f))

    # summary stats in notes
    counts = Counter(r.icp_fit for r in state.fit_results)
    state.notes["fit_counts"] = dict(counts)

    state.qa_flags = flags
    return state
