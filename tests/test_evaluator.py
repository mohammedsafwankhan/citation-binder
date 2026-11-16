"""
Unit tests for the Claim Assessment Flow.
"""

from unittest.mock import patch, AsyncMock
import pytest
from app.services.evaluator import (
    evaluate_claim,
    assess_claim_heuristically,
    Verdict,
    AssessmentOutput,
)
from app.services.passage_selector import select_relevant_passages, Passage
from app.services.quote_verifier import verify_quote_against_source


def get_sample_source_text():
    return (
        "The James Webb Space Telescope (JWST) is a space telescope designed primarily to conduct infrared astronomy. "
        "As the largest optical telescope in space, its high resolution and sensitivity allow it to view objects too old, "
        "distant, or faint for the Hubble Space Telescope.\n\n"
        "The James Webb Space Telescope was successfully launched into space on December 25, 2021 on an Ariane 5 rocket "
        "from Kourou, French Guiana.\n\n"
        "The Apollo 11 mission landed humans on the Moon on July 20, 1969, commanded by Neil Armstrong.\n\n"
        "Python is a high-level programming language conceived in the late 1980s by Guido van Rossum and first released in 1991."
    )


@pytest.fixture
def sample_source_text():
    return get_sample_source_text()


def test_verdict_supports(sample_source_text):
    claim = "The James Webb Space Telescope was launched on December 25, 2021."
    paragraphs = [p.strip() for p in sample_source_text.split("\n\n")]
    passages = select_relevant_passages(claim, paragraphs)

    assert len(passages) > 0
    res = assess_claim_heuristically(claim, passages, sample_source_text)

    assert res.verdict == Verdict.SUPPORTS
    assert len(res.evidence_passages) > 0
    assert any("December 25, 2021" in q for q in res.evidence_passages)


def test_verdict_does_not_support(sample_source_text):
    # Claim asserts landing in 1999, but source states July 20, 1969
    claim = "The Apollo 11 mission landed humans on the Moon in 1999."
    paragraphs = [p.strip() for p in sample_source_text.split("\n\n")]
    passages = select_relevant_passages(claim, paragraphs)

    assert len(passages) > 0
    res = assess_claim_heuristically(claim, passages, sample_source_text)

    assert res.verdict == Verdict.DOES_NOT_SUPPORT
    assert len(res.evidence_passages) > 0


def test_verdict_partially_supports(sample_source_text):
    # Claim gets creator right (Guido van Rossum) but says released in 2015 while source says 1991
    claim = "Python was created by Guido van Rossum in 2015."
    paragraphs = [p.strip() for p in sample_source_text.split("\n\n")]
    passages = select_relevant_passages(claim, paragraphs)

    assert len(passages) > 0
    res = assess_claim_heuristically(claim, passages, sample_source_text)

    assert res.verdict in (Verdict.PARTIALLY_SUPPORTS, Verdict.DOES_NOT_SUPPORT)


def test_verdict_unable_to_verify_when_evidence_missing(sample_source_text):
    # Completely unrelated claim
    claim = "Quantum teleportation was first demonstrated between Mars and Jupiter."
    paragraphs = [p.strip() for p in sample_source_text.split("\n\n")]
    passages = select_relevant_passages(claim, paragraphs)

    res = assess_claim_heuristically(claim, passages, sample_source_text)
    assert res.verdict == Verdict.UNABLE_TO_VERIFY
    assert res.evidence_passages == []


def test_quote_verification_ground_truth(sample_source_text):
    valid_quote = "The James Webb Space Telescope was successfully launched into space on December 25, 2021"
    is_verbatim, ctx, start, end = verify_quote_against_source(valid_quote, sample_source_text)
    assert is_verbatim is True
    assert start is not None
    assert end is not None

    fake_quote = "The James Webb Space Telescope crashed into an asteroid near Mars"
    is_fake_verbatim, _, _, _ = verify_quote_against_source(fake_quote, sample_source_text)
    assert is_fake_verbatim is False


@pytest.mark.asyncio
async def test_missing_credentials_shows_setup_message(sample_source_text):
    """When credentials are not set and fallback is False, shows clear setup message without guessing."""
    claim = "The James Webb Space Telescope was launched in 2021."
    passages = [Passage(index=0, text="Some text", relevance_score=1.0)]

    with patch("app.services.evaluator.settings.GEMINI_API_KEY", ""):
        with patch("app.services.evaluator.settings.OPENAI_API_KEY", ""):
            with patch("app.services.evaluator.settings.LLM_PROVIDER", "gemini"):
                with patch("app.services.evaluator.settings.ALLOW_HEURISTIC_FALLBACK", False):
                    res = await evaluate_claim(claim, passages, sample_source_text)
                    assert res.verdict == Verdict.UNABLE_TO_VERIFY
                    assert "Setup Required" in res.explanation
                    assert "GEMINI_API_KEY" in res.explanation


@pytest.mark.asyncio
async def test_invalid_model_response_returns_unable_to_verify(sample_source_text):
    """If model outputs non-JSON or invalid schema, returns unable to verify."""
    claim = "The James Webb Space Telescope was launched in 2021."
    passages = [Passage(index=0, text=sample_source_text, relevance_score=1.0)]

    with patch("app.services.evaluator.settings.GEMINI_API_KEY", "AIzaSyTestMockKey123"):
        with patch("app.services.evaluator.call_gemini", new=AsyncMock(return_value="NOT_VALID_JSON")):
            res = await evaluate_claim(claim, passages, sample_source_text)
            assert res.verdict == Verdict.UNABLE_TO_VERIFY
            assert "invalid or failed schema validation" in res.explanation


@pytest.mark.asyncio
async def test_never_claim_support_without_source_evidence(sample_source_text):
    """If model claims 'supports' but provides hallucinated quotes not in the source text, downgrades to unable to verify."""
    claim = "The James Webb Space Telescope was launched in 2021."
    passages = [Passage(index=0, text=sample_source_text, relevance_score=1.0)]

    hallucinated_model_json = (
        '{"verdict": "supports", "explanation": "It matches.", "evidence_passages": ["This sentence never existed in the source."]}'
    )

    with patch("app.services.evaluator.settings.GEMINI_API_KEY", "AIzaSyTestMockKey123"):
        with patch("app.services.evaluator.call_gemini", new=AsyncMock(return_value=hallucinated_model_json)):
            res = await evaluate_claim(claim, passages, sample_source_text)
            assert res.verdict == Verdict.UNABLE_TO_VERIFY
            assert "could not be verified verbatim" in res.explanation
            assert res.evidence_passages == []


@pytest.mark.asyncio
async def test_never_claim_partial_support_without_source_evidence(sample_source_text):
    """If model claims 'partially supports' but provides zero valid source quotes, downgrades to unable to verify."""
    claim = "The James Webb Space Telescope was launched in 2021."
    passages = [Passage(index=0, text=sample_source_text, relevance_score=1.0)]

    hallucinated_model_json = (
        '{"verdict": "partially supports", "explanation": "Some partial details.", "evidence_passages": ["Completely hallucinated quote not in text."]}'
    )

    with patch("app.services.evaluator.settings.GEMINI_API_KEY", "AIzaSyTestMockKey123"):
        with patch("app.services.evaluator.call_gemini", new=AsyncMock(return_value=hallucinated_model_json)):
            res = await evaluate_claim(claim, passages, sample_source_text)
            assert res.verdict == Verdict.UNABLE_TO_VERIFY
            assert "could not be verified verbatim" in res.explanation
            assert res.evidence_passages == []
