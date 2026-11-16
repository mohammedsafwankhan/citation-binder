"""
Data Schemas and Request/Response Models for Citation Binder.
"""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
from app.services.evaluator import Verdict
from app.services.quote_verifier import VerifiedQuote


class VerifyClaimRequest(BaseModel):
    claim: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="The factual claim to be checked against the source.",
        examples=["The James Webb Space Telescope was launched on December 25, 2021."]
    )
    url: str = Field(
        ...,
        description="The public web URL of the cited source.",
        examples=["https://en.wikipedia.org/wiki/James_Webb_Space_Telescope"]
    )


class VerificationResponse(BaseModel):
    verdict: Verdict = Field(
        ...,
        description="One of: 'supports', 'partially supports', 'does not support', 'unable to verify'"
    )
    explanation: str = Field(
        ...,
        description="Concise factual explanation justifying the verdict based on source evidence."
    )
    evidence_passages: List[str] = Field(
        default_factory=list,
        description="Exact verbatim evidence passages from the retrieved text backing the verdict."
    )
    quoted_evidence: List[str] = Field(
        default_factory=list,
        description="Alias for evidence_passages for backward compatibility."
    )
    verified_quotes: List[VerifiedQuote] = Field(
        default_factory=list,
        description="Quotes confirmed against original document text with positional character offsets."
    )
    source_link: str = Field(
        ...,
        description="The original user-submitted URL."
    )
    final_url: str = Field(
        ...,
        description="The destination URL after following redirects."
    )
    retrieval_time_ms: float = Field(
        ...,
        description="Time taken to fetch the source in milliseconds."
    )
    total_processing_time_ms: float = Field(
        ...,
        description="Total end-to-end processing latency in milliseconds."
    )
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of when the source was retrieved."
    )
    page_title: Optional[str] = Field(
        default="",
        description="Title of the retrieved web page."
    )
    redirect_count: int = Field(
        default=0,
        description="Number of HTTP redirects traversed."
    )
    passages_analyzed: int = Field(
        default=0,
        description="Number of relevant candidate passages identified and assessed."
    )
    provider: Optional[str] = Field(
        default="system",
        description="The assessment engine or LLM provider used."
    )
    model: Optional[str] = Field(
        default="unknown",
        description="The specific model or algorithm evaluated."
    )
    content_truncated: bool = Field(
        default=False,
        description="True if the source response exceeded the maximum safety size limit."
    )


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
