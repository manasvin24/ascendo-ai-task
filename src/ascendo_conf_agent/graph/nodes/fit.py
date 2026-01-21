from __future__ import annotations

import logging
from ascendo_conf_agent.types import GraphState

log = logging.getLogger(__name__)


def fit_node(state: GraphState) -> GraphState:
    """
    Deprecated: This node is now handled by FitAgent in conversational.py
    Keep for backward compatibility but log warning.
    """
    log.warning("fit_node called directly - use conversational orchestrator instead")
    return state
