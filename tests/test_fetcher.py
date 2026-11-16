"""
Dedicated unit tests for the Server-Side Source Retrieval Layer.
"""

import io
from unittest.mock import patch, AsyncMock
from contextlib import asynccontextmanager
import httpx
import pytest
import pypdf

from app.services.safe_fetcher import (
    retrieve_source,
    RetrievedSource,
    SSRFBlockedError,
    PageUnavailableError,
    TimeoutRetrievalError,
    OversizedContentError,
    UnsupportedContentTypeError,
    EmptyContentError,
)


def make_mock_stream(response: httpx.Response):
    """Creates an async context manager mock for httpx.AsyncClient.stream."""
    cm = AsyncMock()
    cm.__aenter__.return_value = response
    cm.__aexit__.return_value = None
    return cm


@pytest.mark.asyncio
async def test_retrieve_html_document():
    html_content = b"""
    <!DOCTYPE html>
    <html>
        <head><title>Space Missions Overview</title></head>
        <body>
            <main>
                <h1>NASA Flagship Telescopes</h1>
                <p>The James Webb Space Telescope was successfully launched into space on December 25, 2021.</p>
                <p>It operates at the Sun-Earth L2 Lagrange point roughly 1.5 million kilometers from Earth.</p>
            </main>
        </body>
    </html>
    """

    mock_response = httpx.Response(
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        content=html_content,
        request=httpx.Request("GET", "https://example.com/missions")
    )

    with patch("httpx.AsyncClient.stream", return_value=make_mock_stream(mock_response)):
        source = await retrieve_source("https://example.com/missions")

        assert isinstance(source, RetrievedSource)
        assert source.page_title == "Space Missions Overview"
        assert source.final_url == "https://example.com/missions"
        assert "December 25, 2021" in source.extracted_text
        assert len(source.paragraphs) >= 2
        assert source.retrieval_time_ms >= 0
        assert source.is_untrusted_data is True


@pytest.mark.asyncio
async def test_retrieve_pdf_document():
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.add_metadata({"/Title": "Voyager Mission Log"})

    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    mock_response = httpx.Response(
        status_code=200,
        headers={"Content-Type": "application/pdf"},
        content=pdf_bytes,
        request=httpx.Request("GET", "https://example.com/doc.pdf")
    )

    with patch("httpx.AsyncClient.stream", return_value=make_mock_stream(mock_response)):
        with pytest.raises(EmptyContentError):
            await retrieve_source("https://example.com/doc.pdf")


@pytest.mark.asyncio
async def test_reject_unsupported_content_type():
    mock_response = httpx.Response(
        status_code=200,
        headers={"Content-Type": "image/png"},
        content=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
        request=httpx.Request("GET", "https://example.com/chart.png")
    )

    with patch("httpx.AsyncClient.stream", return_value=make_mock_stream(mock_response)):
        with pytest.raises(UnsupportedContentTypeError, match="Unsupported content type"):
            await retrieve_source("https://example.com/chart.png")


@pytest.mark.asyncio
async def test_reject_oversized_response():
    mock_response = httpx.Response(
        status_code=200,
        headers={
            "Content-Type": "text/html",
            "Content-Length": str(10 * 1024 * 1024)  # 10 MB
        },
        content=b"A" * 100,
        request=httpx.Request("GET", "https://example.com/huge.html")
    )

    with patch("httpx.AsyncClient.stream", return_value=make_mock_stream(mock_response)):
        with pytest.raises(OversizedContentError, match="exceeds maximum"):
            await retrieve_source("https://example.com/huge.html", max_bytes=2 * 1024 * 1024)


@pytest.mark.asyncio
async def test_reject_empty_text():
    mock_response = httpx.Response(
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=b"<html><head><title>Empty</title></head><body>    </body></html>",
        request=httpx.Request("GET", "https://example.com/blank.html")
    )

    with patch("httpx.AsyncClient.stream", return_value=make_mock_stream(mock_response)):
        with pytest.raises(EmptyContentError, match="contains no extractable body text"):
            await retrieve_source("https://example.com/blank.html")


@pytest.mark.asyncio
async def test_timeout_handling():
    with patch("httpx.AsyncClient.stream", side_effect=httpx.TimeoutException("Timed out")):
        with pytest.raises(TimeoutRetrievalError, match="timed out"):
            await retrieve_source("https://example.com/slow")


@pytest.mark.asyncio
async def test_reject_unsafe_redirect_hop():
    redirect_response = httpx.Response(
        status_code=302,
        headers={"Location": "http://169.254.169.254/latest/meta-data/"},
        request=httpx.Request("GET", "https://example.com/redirect")
    )

    with patch("httpx.AsyncClient.stream", return_value=make_mock_stream(redirect_response)):
        with pytest.raises(SSRFBlockedError, match="redirect destination blocked"):
            await retrieve_source("https://example.com/redirect")
