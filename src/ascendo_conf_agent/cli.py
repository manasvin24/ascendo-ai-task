from __future__ import annotations

import argparse
import logging
from rich.logging import RichHandler

from ascendo_conf_agent.types import GraphState
from ascendo_conf_agent.conversational import build_conversational_orchestrator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--headless", default="true")
    parser.add_argument("--max-pages", type=int, default=15)
    parser.add_argument("--disable-llm", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    log = logging.getLogger("ascendo_conf_agent")

    state = GraphState(
        seed_url=args.url,
        headless=(str(args.headless).lower() == "true"),
        max_pages=args.max_pages,
        disable_llm=args.disable_llm,
    )

    app = build_conversational_orchestrator()
    final = app.invoke(state)

    # Support both GraphState and plain dict returns
    notes = getattr(final, "notes", None) if final is not None else None
    if notes is None and isinstance(final, dict):
        notes = final.get("notes", {})
    notes = notes or {}

    log.info("Done.")
    log.info(f"Fit counts: {notes.get('fit_counts')}")
    log.info(f"Output: {notes.get('output_path')}")


if __name__ == "__main__":
    main()
