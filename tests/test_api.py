"""
Integration tests for FastAPI endpoints.
"""

from unittest.mock import patch, AsyncMock
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.safe_fetcher import RetrievedSource
from app.services.evaluator import AssessmentOutput, Verdict


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Citation Binder"


@pytest.mark.asyncio
async def test_ssrf_blocking_in_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/verify", json={
            "claim": "Testing SSRF blocking against metadata endpoint",
            "url": "http://169.254.169.254/latest/meta-data/"
        })
        assert response.status_code == 400
        assert "SSRF Protection" in response.json()["detail"]


@pytest.mark.asyncio
async def test_standalone_retrieve_endpoint():
    mock_source = RetrievedSource(
        original_url="https://example.com/page",
        final_url="https://example.com/page",
        status_code=200,
        content_type="text/html",
        page_title="Sample Space Article",
        extracted_text="The James Webb Space Telescope was successfully launched into space on December 25, 2021.",
        paragraphs=["The James Webb Space Telescope was successfully launched into space on December 25, 2021."],
        retrieval_time_ms=85.2,
        byte_count=450,
        is_untrusted_data=True,
        redirect_chain=[],
    )

    with patch("app.main.retrieve_source", new=AsyncMock(return_value=mock_source)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/retrieve", json={
                "url": "https://example.com/page"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["page_title"] == "Sample Space Article"
            assert data["is_untrusted_data"] is True
            assert len(data["paragraphs"]) > 0


@pytest.mark.asyncio
async def test_successful_verification_flow():
    mock_source = RetrievedSource(
        original_url="https://example.com/article",
        final_url="https://example.com/article",
        status_code=200,
        content_type="text/html",
        page_title="Space Exploration",
        extracted_text="The James Webb Space Telescope was successfully launched into space on December 25, 2021.",
        paragraphs=["The James Webb Space Telescope was successfully launched into space on December 25, 2021."],
        retrieval_time_ms=120.5,
        byte_count=500,
        is_untrusted_data=True,
        redirect_chain=[],
    )

    mock_eval = AssessmentOutput(
        verdict=Verdict.SUPPORTS,
        explanation="The source directly confirms the launch.",
        evidence_passages=["The James Webb Space Telescope was successfully launched into space on December 25, 2021."],
        verified_quotes=[],
        confidence=1.0,
        provider="mock-llm",
        model="gemini-1.5-flash",
    )

    with patch("app.main.retrieve_source", new=AsyncMock(return_value=mock_source)):
        with patch("app.main.evaluate_claim", new=AsyncMock(return_value=mock_eval)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/verify", json={
                    "claim": "The James Webb Space Telescope was launched on December 25, 2021.",
                    "url": "https://example.com/article"
                })

                assert response.status_code == 200
                data = response.json()
                assert data["verdict"] == "supports"
                assert len(data["evidence_passages"]) > 0
                assert "December 25, 2021" in data["evidence_passages"][0]
                assert data["final_url"] == "https://example.com/article"
                assert data["retrieval_time_ms"] == 120.5
                assert data["page_title"] == "Space Exploration"
                assert data["provider"] == "mock-llm"
