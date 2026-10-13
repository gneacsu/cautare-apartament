"""Validated data exchanged between the UI, provider and local journal."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Author(StrEnum):
    OWNER = "declarat proprietar"
    AGENCY = "indicii de agenție"
    UNKNOWN = "neclar"


class Status(StrEnum):
    FOUND = "Am găsit posibile anunțuri ale proprietarului."
    NOT_FOUND = "Nu am găsit un anunț al proprietarului în sursele verificate."
    INCOMPLETE = "Nu am putut finaliza verificarea."


class Facts(Record):
    transaction: Literal["vânzare", "închiriere"] | None = None
    city: str | None = None
    area: str | None = None
    address: str | None = None
    rooms: int | None = Field(default=None, ge=1, le=30)
    surface: float | None = Field(default=None, gt=0)
    surface_kind: Literal["utilă", "construită", "necunoscută"] = "necunoscută"
    floor: str | None = None
    layout: str | None = None
    construction_year: int | None = Field(default=None, ge=1600, le=2200)
    price: str | None = None


class Listing(Record):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=12000)
    facts: Facts
    author: Author
    author_evidence: list[str] = Field(max_length=5)
    fragments: list[str] = Field(max_length=3)
    limitations: list[str] = Field(max_length=8)


class SearchHit(Record):
    url: str
    title: str = ""
    snippet: str = ""


class SearchBatch(Record):
    hits: list[SearchHit]
    completed: bool
    limitations: list[str] = Field(default_factory=list)
    executed_queries: list[str] = Field(default_factory=list)
    search_suggestions_html: str = ""


class Source(Record):
    url: str
    final_url: str | None = None
    title: str = ""
    text: str = ""
    access: Literal["page", "snippet", "unavailable", "manual"]
    error: str | None = None
    accessed_at: str


class AssessmentDetails(Record):
    title: str = Field(min_length=1, max_length=300)
    same_property: Literal["probabil", "diferită", "neclar"]
    author: Author
    author_evidence: list[str] = Field(max_length=5)
    evidence: list[str] = Field(max_length=6)
    justification: str = Field(min_length=1, max_length=700)
    facts: Facts
    contradictions: list[str] = Field(max_length=8)


class Assessment(AssessmentDetails):
    url: str


class APICall(Record):
    operation: str
    model: str
    max_output_tokens: int
    thinking_level: str | None = None
    source_count: int | None = None
    outcome: Literal["completed", "error"] = "error"
    finish_reason: str | None = None
    block_reason: str | None = None
    http_status: int | None = None
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


class Comparison(Record):
    status: Literal["completed", "incomplete"]
    source_urls: list[str]
    results: list[Assessment]
    limitations: list[str] = Field(max_length=8)


class Result(Assessment):
    verification: Literal["page", "manual", "snippet"]


class Analysis(Record):
    id: str
    checked_at: str
    input_url: str
    input_text: str
    status: Status = Status.INCOMPLETE
    message: str = ""
    original: Listing | None = None
    results: list[Result] = Field(default_factory=list)
    manual_review: list[Result] = Field(default_factory=list)
    evaluations: list[Assessment] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    executed_queries: list[str] = Field(default_factory=list)
    search_suggestions_html: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    diagnostics: list[APICall] = Field(default_factory=list)
    recovery_hint: str = ""
    limited: bool = False
    limit_reason: str = ""
    coverage: dict[str, int] = Field(default_factory=dict)
