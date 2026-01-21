from __future__ import annotations

import logging

from ascendo_conf_agent.types import GraphState, TargetPage
from ascendo_conf_agent.utils.urls import absolutize, normalize_url

log = logging.getLogger(__name__)

# Forced targets so you never regress to 0 companies again
FORCED = [
    ("/speakers", "speakers"),
    ("/agenda-page/full-agenda", "agenda"),
    ("/agenda-mc", "agenda"),
    ("/sponsors", "logos"),
    ("/mediapartners", "logos"),
    ("/opportunities", "logos"),
]


def planner_node(state: GraphState) -> GraphState:
    seed = normalize_url(state.seed_url)
    if not seed.endswith("/"):
        seed += "/"

    targets: list[TargetPage] = [TargetPage(url=seed, page_type="root")]

    for path, ptype in FORCED:
        targets.append(TargetPage(url=absolutize(seed, path), page_type=ptype))  # type: ignore[arg-type]

    # respect max_pages (including root)
    targets = targets[: max(1, state.max_pages)]

    state.targets = targets
    log.info(f"Planner produced {len(targets)} targets (incl root)")
    for t in targets:
        log.info(f"  target: {t.page_type} -> {t.url}")
    return state
