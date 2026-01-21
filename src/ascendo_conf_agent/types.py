from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PageType = Literal["root", "speakers", "agenda", "logos", "unknown"]


@dataclass
class TargetPage:
    url: str
    page_type: PageType


@dataclass
class RawPage:
    url: str
    page_type: PageType
    html: str


@dataclass
class Evidence:
    url: str
    snippet: str


@dataclass
class CompanyRecord:
    company_name: str
    sources: set[str] = field(default_factory=set)
    evidence: list[Evidence] = field(default_factory=list)
    speakers_count: int = 0


@dataclass
class FitResult:
    company_name: str
    icp_fit: Literal["Yes", "Maybe", "No"]
    confidence: Literal["low", "med", "high"]
    rationale: str


@dataclass
class GraphState:
    seed_url: str
    headless: bool = True
    max_pages: int = 15
    disable_llm: bool = False

    # pipeline data
    targets: list[TargetPage] = field(default_factory=list)
    raw_pages: list[RawPage] = field(default_factory=list)
    company_records: list[CompanyRecord] = field(default_factory=list)
    fit_results: list[FitResult] = field(default_factory=list)

    notes: dict = field(default_factory=dict)
