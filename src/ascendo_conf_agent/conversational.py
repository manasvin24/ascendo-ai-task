from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
import logging
import os

from ascendo_conf_agent.types import GraphState, FitResult, Evidence
from ascendo_conf_agent.graph.nodes.planner import planner_node
from ascendo_conf_agent.graph.nodes.fetcher import fetcher_node
from ascendo_conf_agent.graph.nodes.extractor import extractor_node
from ascendo_conf_agent.graph.nodes.normalizer import normalizer_node
from ascendo_conf_agent.graph.nodes.export import export_node

log = logging.getLogger(__name__)


@dataclass
class Message:
    sender: str
    recipient: str
    content: str
    payload: Optional[dict] = field(default_factory=dict)


class ConversationalAgent:
    """Lightweight agent wrapper around a pipeline node."""
    name: str
    next_agent: Optional[str]
    fn: Optional[Callable[[GraphState], GraphState]]

    def __init__(self, name: str, fn: Optional[Callable[[GraphState], GraphState]], next_agent: Optional[str]):
        self.name = name
        self.fn = fn
        self.next_agent = next_agent

    def handle(self, state: GraphState, msg: Message) -> Tuple[GraphState, Optional[Message]]:
        if self.fn:
            new_state = self.fn(state)
        else:
            new_state = state
            
        if self.next_agent:
            return new_state, Message(sender=self.name, recipient=self.next_agent, content="next")
        return new_state, None


class Orchestrator:
    """Simple message-passing orchestrator for chained agents."""

    def __init__(self, agents: Dict[str, ConversationalAgent], start: str):
        self.agents = agents
        self.start = start

    def invoke(self, state: GraphState) -> GraphState:
        # Ensure notes exists for conversation log and metadata
        if not hasattr(state, "notes") or state.notes is None:
            try:
                state.notes = {}
            except Exception:
                pass

        convo_log: List[dict] = []
        queue: List[Message] = [Message(sender="cli", recipient=self.start, content="start")]
        max_iterations = 100

        iteration = 0
        while queue and iteration < max_iterations:
            iteration += 1
            msg = queue.pop(0)
            
            log.info(f"ORCHESTRATOR: [{iteration}] {msg.sender} → {msg.recipient}: {msg.content}")
            
            convo_log.append({
                "iteration": iteration,
                "from": msg.sender,
                "to": msg.recipient,
                "content": msg.content,
                "payload_keys": list(msg.payload.keys()) if msg.payload else []
            })
            
            agent = self.agents.get(msg.recipient)
            if not agent:
                log.warning(f"ORCHESTRATOR: Agent '{msg.recipient}' not found")
                continue
                
            state, next_msg = agent.handle(state, msg)
            
            if next_msg:
                queue.append(next_msg)

        if hasattr(state, "notes") and isinstance(state.notes, dict):
            state.notes["conversation_log"] = convo_log
            state.notes["conversation_rounds"] = iteration
            log.info(f"ORCHESTRATOR: Completed in {iteration} conversation rounds")
            
        return state


class FitAgent(ConversationalAgent):
    """Initial fit scoring agent that identifies borderline cases."""
    
    def __init__(self):
        super().__init__("fit", None, None)
        self.batch_size = 20
    
    def handle(self, state: GraphState, msg: Message) -> Tuple[GraphState, Optional[Message]]:
        import json
        import os
        from ascendo_conf_agent.llm.client import LLMClient, load_prompt
        
        # Initial LLM scoring
        if state.disable_llm:
            state.fit_results = [
                FitResult(company_name=r.company_name, icp_fit="Maybe", confidence="low", rationale="LLM disabled.")
                for r in state.company_records
            ]
            return state, Message(sender=self.name, recipient="export", content="complete")
        
        # Build cards for LLM
        cards: list[dict] = []
        for rec in state.company_records:
            snips = [e.snippet for e in rec.evidence[:3]]
            cards.append({
                "company_name": rec.company_name,
                "sources": list(rec.sources)[:5],
                "speakers_count": rec.speakers_count,
                "evidence_snippets": snips,
            })
        
        # Batch LLM scoring
        llm_map: dict[str, FitResult] = {}
        if cards:
            log.info(f"FIT: validating {len(cards)} companies via LLM in batches of {self.batch_size}")
            
            prompt_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "llm", "prompts", "prospect_fit_batch.md")
            )
            system = load_prompt(prompt_path)
            client = LLMClient()
            
            for i in range(0, len(cards), self.batch_size):
                batch = cards[i : i + self.batch_size]
                log.info(f"FIT: LLM batch {i//self.batch_size + 1} ({i+1}-{i+len(batch)}/{len(cards)})")
                
                payload = {"companies": batch}
                data = client.json_chat(system=system, user=json.dumps(payload, ensure_ascii=False), max_tokens=1600)
                
                for r in (data.get("results") or []):
                    name = (r.get("company_name") or "").strip()
                    if not name:
                        continue
                    icp_fit = r.get("icp_fit")
                    conf = r.get("confidence")
                    rationale = (r.get("rationale") or "").strip()
                    
                    if icp_fit not in {"Yes", "Maybe", "No"}:
                        continue
                    if conf not in {"low", "med", "high"}:
                        conf = "low"
                    
                    llm_map[name] = FitResult(
                        company_name=name,
                        icp_fit=icp_fit,
                        confidence=conf,
                        rationale=rationale[:220],
                    )
        
        # Merge results
        out: list[FitResult] = []
        for rec in state.company_records:
            out.append(
                llm_map.get(
                    rec.company_name,
                    FitResult(company_name=rec.company_name, icp_fit="Maybe", confidence="low", rationale="No LLM row returned."),
                )
            )
        
        state.fit_results = out
        
        # Identify borderline cases
        borderline = [
            r.company_name for r in state.fit_results
            if r.icp_fit == "Maybe" and r.confidence in ["low", "med"]
        ]
        
        if not borderline:
            log.info(f"FIT: No enrichment needed (0 borderline cases)")
            self._update_fit_counts(state)
            return state, Message(sender=self.name, recipient="export", content="complete")
        
        # Send enrichment request in batches
        log.info(f"FIT: Requesting enrichment for {len(borderline)} borderline companies")
        
        # Write ICP scoring artifact (CSV 2) before enrichment
        self._write_icp_artifact(state, stage="initial")
        
        return state, Message(
            sender=self.name,
            recipient="enrichment",
            content="enrich_request",
            payload={"borderline_companies": borderline[:10]}  # Limit to 10
        )
    
    def _write_icp_artifact(self, state: GraphState, stage: str) -> None:
        """Write ICP scored companies to CSV for agent handoff."""
        import os
        import pandas as pd
        from ascendo_conf_agent.config import SETTINGS
        
        os.makedirs(SETTINGS.output_dir, exist_ok=True)
        
        rows = []
        for result in state.fit_results:
            rows.append({
                "company_name": result.company_name,
                "icp_fit": result.icp_fit,
                "confidence": result.confidence,
                "rationale": result.rationale,
                "scored_at": pd.Timestamp.now().isoformat()
            })
        
        df = pd.DataFrame(rows)
        csv_path = os.path.join(SETTINGS.output_dir, f"stage2_icp_{stage}.csv")
        df.to_csv(csv_path, index=False)
        
        if not hasattr(state, "notes") or state.notes is None:
            state.notes = {}
        state.notes[f"icp_artifact_{stage}"] = csv_path
        
        log.info(f"ARTIFACT: Wrote {len(rows)} ICP scores to {csv_path}")
    
    def _update_fit_counts(self, state: GraphState) -> None:
        counts: dict[str, int] = {"Yes": 0, "Maybe": 0, "No": 0}
        for r in state.fit_results:
            counts[r.icp_fit] = counts.get(r.icp_fit, 0) + 1
        
        if not hasattr(state, "notes") or state.notes is None:
            try:
                state.notes = {}
            except Exception:
                return
        
        if isinstance(state.notes, dict):
            state.notes["fit_counts"] = counts
        
        log.info(f"FIT: Yes: {counts['Yes']}, Maybe: {counts['Maybe']}, No: {counts['No']}")


class EnrichmentAgent(ConversationalAgent):
    """Searches existing pages for additional evidence on borderline companies."""
    
    def __init__(self):
        super().__init__("enrichment", None, "fit_rescore")
    
    def handle(self, state: GraphState, msg: Message) -> Tuple[GraphState, Optional[Message]]:
        borderline_companies = msg.payload.get("borderline_companies", [])
        
        if not borderline_companies:
            log.info("ENRICHMENT: No companies to enrich")
            return state, Message(sender=self.name, recipient="export", content="skip")
        
        log.info(f"ENRICHMENT: Searching for evidence on {len(borderline_companies)} companies")
        
        # Load extraction artifact (CSV 1) to access original evidence
        extraction_csv = state.notes.get("extraction_artifact")
        if extraction_csv and os.path.exists(extraction_csv):
            import pandas as pd
            extraction_df = pd.read_csv(extraction_csv)
            log.info(f"ENRICHMENT: Loaded {len(extraction_df)} companies from extraction artifact")
        
        enriched_companies = []
        seed_url = state.seed_url.rstrip('/')
        search_targets = ["/sponsors", "/mediapartners", "/partners", "/exhibitors"]
        
        # Search existing pages only (no new fetches)
        for company_name in borderline_companies:
            evidence_found = []
            
            for path in search_targets:
                full_url = seed_url + path
                
                for rp in state.raw_pages:
                    if rp.url == full_url and rp.html and company_name.lower() in rp.html.lower():
                        idx = rp.html.lower().find(company_name.lower())
                        snippet = rp.html[max(0, idx-100):idx+100]
                        evidence_found.append(Evidence(
                            url=full_url,
                            snippet=snippet
                        ))
                        log.info(f"ENRICHMENT: Found evidence for {company_name} in {full_url}")
                        break
            
            if evidence_found:
                # Add evidence to company record
                for rec in state.company_records:
                    if rec.company_name == company_name:
                        rec.evidence.extend(evidence_found[:2])  # Top 2 pieces
                        enriched_companies.append(company_name)
                        break
        
        log.info(f"ENRICHMENT: Found evidence for {len(enriched_companies)}/{len(borderline_companies)} companies")
        
        # Write enriched companies back to updated extraction artifact
        self._write_enriched_artifact(state, enriched_companies)
        
        # Send enriched companies for re-scoring
        return state, Message(
            sender=self.name,
            recipient="fit_rescore",
            content="rescore_request",
            payload={"enriched_companies": enriched_companies}
        )
    
    def _write_enriched_artifact(self, state: GraphState, enriched_companies: list[str]) -> None:
        """Update extraction artifact with enriched evidence."""
        import pandas as pd
        import os
        from ascendo_conf_agent.config import SETTINGS
        
        os.makedirs(SETTINGS.output_dir, exist_ok=True)
        
        rows = []
        for rec in state.company_records:
            if rec.company_name in enriched_companies:
                evidence_urls = [e.url for e in rec.evidence]
                evidence_snippets = [e.snippet[:100] for e in rec.evidence[:5]]
                
                rows.append({
                    "company_name": rec.company_name,
                    "speakers_count": rec.speakers_count,
                    "source_pages": "; ".join(sorted(rec.sources)),
                    "evidence_urls": " | ".join(evidence_urls[:10]),
                    "evidence_snippets": " | ".join(evidence_snippets),
                    "enriched": True,
                    "enriched_at": pd.Timestamp.now().isoformat()
                })
        
        if rows:
            df = pd.DataFrame(rows)
            csv_path = os.path.join(SETTINGS.output_dir, "stage1_enriched_companies.csv")
            df.to_csv(csv_path, index=False)
            state.notes["enriched_artifact"] = csv_path
            log.info(f"ARTIFACT: Wrote {len(rows)} enriched companies to {csv_path}")


class FitRescoreAgent(ConversationalAgent):
    """Re-scores companies that received additional evidence."""
    
    def __init__(self):
        super().__init__("fit_rescore", None, "export")
        self.batch_size = 20
    
    def handle(self, state: GraphState, msg: Message) -> Tuple[GraphState, Optional[Message]]:
        enriched_companies = msg.payload.get("enriched_companies", [])
        
        if not enriched_companies:
            log.info("FIT_RESCORE: No companies to rescore")
            self._update_fit_counts(state)
            return state, Message(sender=self.name, recipient="export", content="complete")
        
        log.info(f"FIT_RESCORE: Re-scoring {len(enriched_companies)} enriched companies")
        
        import json
        import os
        from ascendo_conf_agent.llm.client import LLMClient, load_prompt
        
        # Build cards for enriched companies
        rescore_cards = []
        for rec in state.company_records:
            if rec.company_name in enriched_companies:
                snips = [e.snippet for e in rec.evidence[:5]]  # Include new evidence
                rescore_cards.append({
                    "company_name": rec.company_name,
                    "sources": list(rec.sources)[:5],
                    "speakers_count": rec.speakers_count,
                    "evidence_snippets": snips,
                })
        
        # Re-run LLM in batches
        rescore_map = {}
        if rescore_cards:
            prompt_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "llm", "prompts", "prospect_fit_batch.md")
            )
            system = load_prompt(prompt_path)
            client = LLMClient()
            
            for i in range(0, len(rescore_cards), self.batch_size):
                batch = rescore_cards[i : i + self.batch_size]
                log.info(f"FIT_RESCORE: batch {i//self.batch_size + 1} ({i+1}-{i+len(batch)}/{len(rescore_cards)})")
                
                payload = {"companies": batch}
                data = client.json_chat(system=system, user=json.dumps(payload, ensure_ascii=False), max_tokens=1600)
                
                for r in (data.get("results") or []):
                    name = (r.get("company_name") or "").strip()
                    if not name:
                        continue
                    icp_fit = r.get("icp_fit")
                    conf = r.get("confidence")
                    rationale = (r.get("rationale") or "").strip()
                    
                    if icp_fit not in {"Yes", "Maybe", "No"}:
                        continue
                    if conf not in {"low", "med", "high"}:
                        conf = "low"
                    
                    rescore_map[name] = FitResult(
                        company_name=name,
                        icp_fit=icp_fit,
                        confidence=conf,
                        rationale=rationale[:220],
                    )
        
        # Update fit results
        changes = 0
        for i, result in enumerate(state.fit_results):
            if result.company_name in rescore_map:
                old_fit = result.icp_fit
                new_result = rescore_map[result.company_name]
                state.fit_results[i] = new_result
                
                if old_fit != new_result.icp_fit:
                    log.info(f"FIT_RESCORE: {result.company_name} changed from {old_fit} to {new_result.icp_fit}")
                    changes += 1
        
        log.info(f"FIT_RESCORE: {changes} companies changed classification")
        self._update_fit_counts(state)
        
        # Write final ICP artifact (CSV 2 - rescored)
        self._write_final_icp_artifact(state)
        
        return state, Message(sender=self.name, recipient="export", content="complete")
    
    def _write_final_icp_artifact(self, state: GraphState) -> None:
        """Write final rescored ICP results to CSV."""
        import os
        import pandas as pd
        from ascendo_conf_agent.config import SETTINGS
        
        os.makedirs(SETTINGS.output_dir, exist_ok=True)
        
        rows = []
        for result in state.fit_results:
            rows.append({
                "company_name": result.company_name,
                "icp_fit": result.icp_fit,
                "confidence": result.confidence,
                "rationale": result.rationale,
                "scored_at": pd.Timestamp.now().isoformat()
            })
        
        df = pd.DataFrame(rows)
        csv_path = os.path.join(SETTINGS.output_dir, "stage2_icp_final.csv")
        df.to_csv(csv_path, index=False)
        
        if not hasattr(state, "notes") or state.notes is None:
            state.notes = {}
        state.notes["icp_artifact_final"] = csv_path
        
        log.info(f"ARTIFACT: Wrote {len(rows)} final ICP scores to {csv_path}")
    
    def _update_fit_counts(self, state: GraphState) -> None:
        counts: dict[str, int] = {"Yes": 0, "Maybe": 0, "No": 0}
        for r in state.fit_results:
            counts[r.icp_fit] = counts.get(r.icp_fit, 0) + 1
        
        if not hasattr(state, "notes") or state.notes is None:
            try:
                state.notes = {}
            except Exception:
                return
        
        if isinstance(state.notes, dict):
            state.notes["fit_counts"] = counts
        
        log.info(f"FIT_RESCORE: Final counts - Yes: {counts['Yes']}, Maybe: {counts['Maybe']}, No: {counts['No']}")


def build_conversational_orchestrator() -> Orchestrator:
    """Build orchestrator with enrichment conversation loop."""
    agents = {
        "planner": ConversationalAgent("planner", planner_node, "fetcher"),
        "fetcher": ConversationalAgent("fetcher", fetcher_node, "extractor"),
        "extractor": ConversationalAgent("extractor", extractor_node, "normalizer"),
        "normalizer": ConversationalAgent("normalizer", normalizer_node, "fit"),
        "fit": FitAgent(),
        "enrichment": EnrichmentAgent(),
        "fit_rescore": FitRescoreAgent(),
        "export": ConversationalAgent("export", export_node, None),
    }
    return Orchestrator(agents=agents, start="planner")
