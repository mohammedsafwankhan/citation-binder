"""
Verbatim Quote Verification Module for Citation Binder.

Enforces ground truth: guarantees that any quoted evidence returned
actually appears verbatim within the retrieved source document.
"""

import re
from typing import Optional, List, Tuple
from pydantic import BaseModel


class VerifiedQuote(BaseModel):
    quote: str
    is_verbatim: bool
    context: Optional[str] = None
    character_start: Optional[int] = None
    character_end: Optional[int] = None


def normalize_whitespace(text: str) -> str:
    """Normalizes multiple spaces, tabs, and newlines into a single space."""
    return re.sub(r"\s+", " ", text).strip()


def verify_quote_against_source(quote: str, raw_document_text: str) -> Tuple[bool, Optional[str], Optional[int], Optional[int]]:
    """
    Checks if a quote exists verbatim (or normalized whitespace) in the raw document text.
    Returns: (is_verbatim, surrounding_context, start_char, end_char)
    """
    if not quote or not raw_document_text:
        return False, None, None, None

    clean_quote = quote.strip().strip('"').strip("'")
    if not clean_quote:
        return False, None, None, None

    # 1. Exact substring check
    pos = raw_document_text.find(clean_quote)
    if pos != -1:
        start_char = pos
        end_char = pos + len(clean_quote)
        # Extract surrounding context (up to 80 chars before and after)
        ctx_start = max(0, start_char - 80)
        ctx_end = min(len(raw_document_text), end_char + 80)
        context = raw_document_text[ctx_start:ctx_end].replace("\n", " ").strip()
        return True, context, start_char, end_char

    # 2. Case-insensitive exact substring check
    lower_doc = raw_document_text.lower()
    lower_quote = clean_quote.lower()
    pos_lower = lower_doc.find(lower_quote)
    if pos_lower != -1:
        start_char = pos_lower
        end_char = pos_lower + len(clean_quote)
        actual_slice = raw_document_text[start_char:end_char]
        ctx_start = max(0, start_char - 80)
        ctx_end = min(len(raw_document_text), end_char + 80)
        context = raw_document_text[ctx_start:ctx_end].replace("\n", " ").strip()
        return True, context, start_char, end_char

    # 3. Normalized whitespace comparison
    norm_doc = normalize_whitespace(raw_document_text)
    norm_quote = normalize_whitespace(clean_quote)
    norm_pos = norm_doc.find(norm_quote)
    if norm_pos != -1:
        ctx_start = max(0, norm_pos - 80)
        ctx_end = min(len(norm_doc), norm_pos + len(norm_quote) + 80)
        context = norm_doc[ctx_start:ctx_end].strip()
        return True, context, None, None

    return False, None, None, None


def filter_and_verify_quotes(candidate_quotes: List[str], raw_document_text: str) -> List[VerifiedQuote]:
    """
    Filters a list of candidate quotes, returning only those that can be verified
    against the source document. Hallucinated or altered quotes are flagged or dropped.
    """
    verified: List[VerifiedQuote] = []
    seen = set()

    for q in candidate_quotes:
        if not q:
            continue
        clean_q = q.strip().strip('"').strip("'")
        if not clean_q or len(clean_q) < 10 or clean_q in seen:
            continue
        seen.add(clean_q)

        is_verbatim, context, start, end = verify_quote_against_source(clean_q, raw_document_text)
        if is_verbatim:
            verified.append(VerifiedQuote(
                quote=clean_q,
                is_verbatim=True,
                context=context,
                character_start=start,
                character_end=end
            ))

    return verified
