"""
Server-Side Source Retrieval Layer for Citation Binder.

Architecture & Responsibilities:
- Strictly decoupled from UI and claim assessment logic.
- Enforces public HTTP/HTTPS access only, blocking private/internal/metadata IPs.
- Validates every hop in redirect chains against SSRF guards.
- Enforces request timeouts (connect & read) and true streaming response size limits (aborting early).
- Extracts readable text from HTML, plain text, and text-based PDF documents.
- Treats all fetched content strictly as untrusted data (never instructions).
- Raises clear, structured errors for unavailable, unsupported, oversized, or empty sources.
"""

import io
import re
import time
from urllib.parse import urljoin, urlparse
from typing import Optional, List, Tuple
import httpx
from pydantic import BaseModel, Field

from app.services.ssrf_guard import validate_url, SSRFValidationError, DNSResolutionError
from app.services.extractor import extract_content_from_html

try:
    import pypdf
    PDF_SUPPORTED = True
except ImportError:
    PDF_SUPPORTED = False


# Defaults and Configuration
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_CONNECT_TIMEOUT = 3.0
CHUNK_SIZE = 16384  # 16 KB chunks for streaming
USER_AGENT = "CitationBinder/1.0 (+https://github.com/citation-binder; verification-bot)"

# Whitelist of allowed Content-Type prefixes/matches
ALLOWED_CONTENT_TYPES = [
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
    "text/markdown",
    "application/pdf",
    "application/x-pdf",
]

# Explicitly disallowed binary content types
DISALLOWED_CONTENT_PREFIXES = [
    "image/",
    "audio/",
    "video/",
    "application/zip",
    "application/x-tar",
    "application/x-rar",
    "application/x-7z-compressed",
    "application/octet-stream",
    "application/x-msdownload",
    "application/x-executable",
]


# ==========================================
# Typed Exception Hierarchy
# ==========================================

class RetrievalError(Exception):
    """Base exception for all source retrieval errors."""
    def __init__(self, message: str, url: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.url = url
        self.status_code = status_code


class SSRFBlockedError(RetrievalError):
    """Raised when URL points to a forbidden private, loopback, or metadata IP."""
    pass


class PageUnavailableError(RetrievalError):
    """Raised when the target page is unreachable, returns 404/500, or drops connection."""
    pass


class TimeoutRetrievalError(RetrievalError):
    """Raised when connection or read operation exceeds timeout."""
    pass


class OversizedContentError(RetrievalError):
    """Raised when response body exceeds maximum allowed byte limit."""
    pass


class UnsupportedContentTypeError(RetrievalError):
    """Raised when response is a binary or media format (image, audio, zip, etc.)."""
    pass


class EmptyContentError(RetrievalError):
    """Raised when extracted document contains no readable text."""
    pass


# Legacy alias
FetchError = RetrievalError


# ==========================================
# Models
# ==========================================

class RedirectHop(BaseModel):
    url: str
    status_code: int


class RetrievedSource(BaseModel):
    original_url: str
    final_url: str
    status_code: int
    content_type: str
    page_title: str
    extracted_text: str
    paragraphs: List[str]
    retrieval_time_ms: float
    byte_count: int
    is_untrusted_data: bool = Field(
        default=True,
        description="Explicit flag ensuring fetched text is treated as untrusted payload data, never instructions."
    )
    redirect_chain: List[RedirectHop] = Field(default_factory=list)


# Legacy alias
FetchResult = RetrievedSource


# ==========================================
# Helpers for Text & PDF Extraction
# ==========================================

def sanitize_untrusted_text(text: str) -> str:
    """
    Strips harmful ASCII control characters (except newline, tab, carriage return)
    to prevent terminal/rendering injection and ensure clean plain text.
    """
    if not text:
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def extract_text_from_pdf(pdf_bytes: bytes) -> Tuple[str, str, List[str]]:
    """Extracts text and title from text-based PDF bytes using pypdf."""
    if not PDF_SUPPORTED:
        raise UnsupportedContentTypeError(
            "PDF extraction requested, but pypdf library is not installed.",
            url=""
        )

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise UnsupportedContentTypeError(
                    "Encrypted or password-protected PDF files cannot be verified.",
                    url=""
                )

        title = ""
        if reader.metadata and reader.metadata.title:
            title = str(reader.metadata.title).strip()

        paragraphs: List[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            for block in page_text.split("\n\n"):
                clean_block = re.sub(r"\s+", " ", block).strip()
                if len(clean_block) >= 20 and len(clean_block.split()) >= 3:
                    paragraphs.append(clean_block)

        full_text = "\n\n".join(paragraphs)
        return title, full_text, paragraphs

    except (UnsupportedContentTypeError, PageUnavailableError):
        raise
    except Exception as e:
        raise PageUnavailableError(
            f"Failed to extract readable text from PDF: {str(e)}",
            url=""
        )


def is_content_type_allowed(content_type_header: str) -> bool:
    """Checks whether the Content-Type header matches allowed document types."""
    ct_clean = content_type_header.lower().split(";")[0].strip()

    for disallowed in DISALLOWED_CONTENT_PREFIXES:
        if ct_clean.startswith(disallowed):
            return False

    for allowed in ALLOWED_CONTENT_TYPES:
        if ct_clean == allowed or ct_clean.startswith(allowed):
            return True

    return False


# ==========================================
# Core Retrieval Function with Early Streaming Abort
# ==========================================

async def retrieve_source(
    url: str,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_bytes: int = DEFAULT_MAX_BODY_BYTES,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> RetrievedSource:
    """
    Safely retrieves and parses a public web document (HTML, Plaintext, PDF).
    Completely isolated from claim evaluation.

    Enforces:
    - Pre-flight SSRF prevention & DNS re-validation per redirect hop
    - Streaming byte consumption with early abort on oversized bodies
    - Connect and read timeouts
    - Rejection of binary/media content
    - Untrusted data containment
    """
    start_time = time.perf_counter()

    # 1. SSRF Validation of initial URL
    try:
        current_url, _ = validate_url(url)
    except SSRFValidationError as e:
        raise SSRFBlockedError(f"Security block: {str(e)}", url=url)
    except DNSResolutionError as e:
        raise PageUnavailableError(f"Domain resolution failed: {str(e)}", url=url)

    original_url = current_url
    redirect_chain: List[RedirectHop] = []

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9",
    }

    transport = httpx.AsyncHTTPTransport(retries=1)
    timeout_config = httpx.Timeout(timeout, connect=DEFAULT_CONNECT_TIMEOUT, read=timeout)

    async with httpx.AsyncClient(transport=transport, timeout=timeout_config, follow_redirects=False) as client:
        redirect_count = 0

        while True:
            try:
                # Open request with streaming to prevent buffering oversized responses into memory
                async with client.stream("GET", current_url, headers=headers) as response:

                    # Handle Redirects
                    if response.is_redirect:
                        redirect_count += 1
                        if redirect_count > max_redirects:
                            raise PageUnavailableError(
                                f"Too many redirects (exceeded limit of {max_redirects})",
                                url=current_url,
                                status_code=response.status_code
                            )

                        redirect_chain.append(RedirectHop(url=current_url, status_code=response.status_code))
                        location = response.headers.get("Location")
                        if not location:
                            raise PageUnavailableError(
                                "Redirect response missing Location header",
                                url=current_url,
                                status_code=response.status_code
                            )

                        next_url = urljoin(current_url, location)

                        # Re-validate redirect destination against SSRF rules before next hop
                        try:
                            current_url, _ = validate_url(next_url)
                        except SSRFValidationError as e:
                            raise SSRFBlockedError(
                                f"Unsafe redirect destination blocked: {str(e)}",
                                url=next_url
                            )
                        except DNSResolutionError as e:
                            raise PageUnavailableError(
                                f"Redirect domain resolution failed: {str(e)}",
                                url=next_url
                            )

                        continue

                    # Non-redirect response reached: Check HTTP Status
                    if response.status_code >= 400:
                        raise PageUnavailableError(
                            f"Source returned HTTP error status {response.status_code}",
                            url=current_url,
                            status_code=response.status_code
                        )

                    content_type_header = response.headers.get("Content-Type", "")

                    is_pdf = (
                        "application/pdf" in content_type_header.lower()
                        or urlparse(current_url).path.lower().endswith(".pdf")
                    )

                    # Validate Content-Type
                    if content_type_header and not is_pdf:
                        if not is_content_type_allowed(content_type_header):
                            raise UnsupportedContentTypeError(
                                f"Unsupported content type '{content_type_header}'. Only web pages (HTML), text, and PDF documents are supported.",
                                url=current_url,
                                status_code=response.status_code
                            )

                    # Check Content-Length header early
                    content_length_header = response.headers.get("Content-Length")
                    if content_length_header:
                        try:
                            cl_bytes = int(content_length_header)
                            if cl_bytes > max_bytes:
                                raise OversizedContentError(
                                    f"Source document ({cl_bytes / (1024*1024):.1f} MB) exceeds maximum allowed size limit ({max_bytes / (1024*1024):.1f} MB).",
                                    url=current_url,
                                    status_code=response.status_code
                                )
                        except ValueError:
                            pass

                    # Stream bytes in chunks with hard abort if size limit is crossed
                    byte_chunks: List[bytes] = []
                    total_bytes = 0

                    async for chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE):
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise OversizedContentError(
                                f"Source document body exceeded maximum size limit ({max_bytes / (1024*1024):.1f} MB) during download.",
                                url=current_url,
                                status_code=response.status_code
                            )
                        byte_chunks.append(chunk)

                    raw_bytes = b"".join(byte_chunks)
                    encoding = response.encoding or "utf-8"
                    status_code = response.status_code

                    # We have successfully read the body of the final destination
                    break

            except httpx.TimeoutException:
                raise TimeoutRetrievalError(
                    f"Request timed out after {timeout:.1f}s while retrieving {current_url}",
                    url=current_url
                )
            except httpx.RequestError as e:
                raise PageUnavailableError(
                    f"Network connection failed for {current_url}: {str(e)}",
                    url=current_url
                )

        # Extract Text based on content type
        page_title = ""
        extracted_text = ""
        paragraphs: List[str] = []

        if is_pdf:
            page_title, extracted_text, paragraphs = extract_text_from_pdf(raw_bytes)
            if not page_title:
                page_title = urlparse(current_url).path.split("/")[-1] or "PDF Document"
        else:
            try:
                decoded_str = raw_bytes.decode(encoding, errors="replace")
            except Exception:
                decoded_str = raw_bytes.decode("utf-8", errors="replace")

            doc = extract_content_from_html(decoded_str)
            page_title = doc.title
            extracted_text = doc.full_text
            paragraphs = doc.paragraphs

        # Sanitize untrusted content (remove non-printable control chars)
        extracted_text = sanitize_untrusted_text(extracted_text)
        paragraphs = [sanitize_untrusted_text(p) for p in paragraphs if p.strip()]

        # Validate that readable text was extracted
        if not extracted_text.strip() or len(extracted_text.strip()) < 25:
            raise EmptyContentError(
                "The source was retrieved successfully, but contains no extractable body text (may be empty, JavaScript-rendered, or an image-only scan).",
                url=current_url,
                status_code=status_code
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return RetrievedSource(
            original_url=original_url,
            final_url=current_url,
            status_code=status_code,
            content_type=content_type_header or ("application/pdf" if is_pdf else "text/html"),
            page_title=page_title or "Untitled Document",
            extracted_text=extracted_text,
            paragraphs=paragraphs,
            retrieval_time_ms=round(elapsed_ms, 2),
            byte_count=len(raw_bytes),
            is_untrusted_data=True,
            redirect_chain=redirect_chain,
        )


# Backward-compatible alias
async def safe_fetch_url(url: str, **kwargs) -> RetrievedSource:
    return await retrieve_source(url, **kwargs)
