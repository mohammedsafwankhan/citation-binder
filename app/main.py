"""
Citation Binder - Main FastAPI Application.

Orchestrates:
1. URL validation & SSRF protection
2. Safe network retrieval with redirect tracking and PDF/HTML text extraction
3. Content extraction and passage selection
4. Claim assessment and verbatim quote verification
5. Web UI serving and REST API endpoints
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.schemas import VerifyClaimRequest, VerificationResponse, HealthResponse
from app.services.ssrf_guard import SSRFValidationError
from app.services.safe_fetcher import (
    retrieve_source,
    safe_fetch_url,
    RetrievedSource,
    RetrievalError,
    SSRFBlockedError,
    PageUnavailableError,
    TimeoutRetrievalError,
    OversizedContentError,
    UnsupportedContentTypeError,
    EmptyContentError,
)
from app.services.passage_selector import select_relevant_passages
from app.services.evaluator import evaluate_claim, Verdict

# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Checks whether a cited public source supports, partially supports, does not support, or is unable to verify a claim."
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Enforces standard HTTP defensive security headers."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "img-src 'self' data:;"
    )
    return response


class RetrieveOnlyRequest(BaseModel):
    url: str = Field(..., description="The public web URL or text-based PDF to retrieve.")


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
    )


@app.post("/api/retrieve", response_model=RetrievedSource)
async def retrieve_only(payload: RetrieveOnlyRequest):
    """
    Dedicated endpoint for the isolated server-side source retrieval layer.
    Retrieves, parses, and extracts text from a public web page or PDF
    without performing claim evaluation.
    """
    try:
        source = await retrieve_source(
            url=payload.url,
            max_redirects=settings.MAX_REDIRECTS,
            max_bytes=settings.MAX_BODY_BYTES,
            timeout=settings.FETCH_TIMEOUT,
        )
        return source
    except SSRFBlockedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security rejection (SSRF Protection): {e.message}"
        )
    except UnsupportedContentTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=e.message
        )
    except OversizedContentError as e:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=e.message
        )
    except (PageUnavailableError, TimeoutRetrievalError, EmptyContentError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=e.message
        )


@app.post("/api/verify", response_model=VerificationResponse)
async def verify_citation(payload: VerifyClaimRequest):
    """
    Core verification endpoint:
    Checks whether the source at payload.url supports, partially supports,
    contradicts, or is unable to verify payload.claim.
    """
    total_start_time = time.perf_counter()
    claim_text = payload.claim.strip()
    source_url = payload.url.strip()

    # Step 1: Server-Side Source Retrieval (Isolated Layer)
    try:
        source = await retrieve_source(
            url=source_url,
            max_redirects=settings.MAX_REDIRECTS,
            max_bytes=settings.MAX_BODY_BYTES,
            timeout=settings.FETCH_TIMEOUT,
        )
    except (SSRFBlockedError, SSRFValidationError) as e:
        # Security violation (SSRF attempt) -> return HTTP 400 Bad Request
        msg = getattr(e, "message", str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security rejection (SSRF Protection): {msg}"
        )
    except (RetrievalError, PageUnavailableError, TimeoutRetrievalError, OversizedContentError, UnsupportedContentTypeError, EmptyContentError) as e:
        # Retrieval failed or document invalid -> Return unable to verify with clear explanation
        total_time_ms = (time.perf_counter() - total_start_time) * 1000
        return VerificationResponse(
            verdict=Verdict.UNABLE_TO_VERIFY,
            explanation=f"Source retrieval error: {e.message}",
            quoted_evidence=[],
            verified_quotes=[],
            source_link=source_url,
            final_url=getattr(e, "url", source_url),
            retrieval_time_ms=round(total_time_ms, 2),
            total_processing_time_ms=round(total_time_ms, 2),
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            page_title="Retrieval Failed",
            redirect_count=0,
            passages_analyzed=0,
            content_truncated=False,
        )

    # Step 2: Passage Selection and Relevance Filtering
    candidate_passages = select_relevant_passages(
        claim=claim_text,
        paragraphs=source.paragraphs,
        top_k=settings.TOP_K_PASSAGES,
        min_score_threshold=settings.MIN_RELEVANCE_SCORE,
    )

    # Step 3: Claim Assessment (Isolated from retrieval)
    evaluation = await evaluate_claim(
        claim=claim_text,
        passages=candidate_passages,
        raw_document=source.extracted_text,
    )

    total_time_ms = (time.perf_counter() - total_start_time) * 1000

    return VerificationResponse(
        verdict=evaluation.verdict,
        explanation=evaluation.explanation,
        evidence_passages=evaluation.evidence_passages,
        quoted_evidence=evaluation.evidence_passages,
        verified_quotes=evaluation.verified_quotes,
        source_link=source.original_url,
        final_url=source.final_url,
        retrieval_time_ms=source.retrieval_time_ms,
        total_processing_time_ms=round(total_time_ms, 2),
        retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
        page_title=source.page_title,
        redirect_count=len(source.redirect_chain),
        passages_analyzed=len(candidate_passages),
        provider=evaluation.provider,
        model=evaluation.model,
        content_truncated=False,
    )


# Mount Static Files for Web UI
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/report.pdf")
    async def get_report_pdf():
        """Serves the complete project technical report in PDF format."""
        pdf_file = static_dir / "Citation_Binder_Project_Report.pdf"
        if pdf_file.exists():
            return FileResponse(
                str(pdf_file),
                media_type="application/pdf",
                filename="Citation_Binder_Project_Report.pdf",
                content_disposition_type="inline"
            )
        raise HTTPException(status_code=404, detail="Report PDF not found")

    @app.get("/presentation.pdf")
    async def get_presentation_pdf():
        """Serves the 16:9 widescreen presentation slide deck in PDF format."""
        pdf_file = static_dir / "Citation_Binder_Presentation.pdf"
        if pdf_file.exists():
            return FileResponse(
                str(pdf_file),
                media_type="application/pdf",
                filename="Citation_Binder_Presentation.pdf",
                content_disposition_type="inline"
            )
        raise HTTPException(status_code=404, detail="Presentation PDF not found")

    @app.get("/presentation.pptx")
    async def get_presentation_pptx():
        """Serves the PowerPoint slide deck in PPTX format."""
        pptx_file = static_dir / "Citation_Binder_Presentation.pptx"
        if pptx_file.exists():
            return FileResponse(
                str(pptx_file),
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                filename="Citation_Binder_Presentation.pptx"
            )
        raise HTTPException(status_code=404, detail="Presentation PPTX not found")

    @app.get("/")
    async def serve_index():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse({"message": f"{settings.APP_NAME} API is running. Static UI not found."})
