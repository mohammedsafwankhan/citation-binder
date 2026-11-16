"""
Content Extraction and Normalization Module for Citation Binder.

Extracts meaningful textual content from raw HTML while stripping:
- Scripts, styles, noscript, and embeds
- Boilerplate navigation, headers, footers, and sidebars
- Ads and metadata widgets
"""

import re
from typing import List, Optional
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field


class ExtractedDocument(BaseModel):
    title: str = ""
    paragraphs: List[str] = Field(default_factory=list)
    full_text: str = ""
    word_count: int = 0


# Tags that are definitely non-content or boilerplate
BOILERPLATE_TAGS = [
    "script", "style", "noscript", "svg", "iframe", "canvas",
    "nav", "header", "footer", "aside", "form", "button",
    "dialog", "menu", "template"
]

# Common ad/widget class and id regex patterns
NOISE_PATTERN = re.compile(
    r"(cookie|banner|consent|sidebar|widget|advertisement|newsletter|social-share|popup|modal)",
    re.IGNORECASE
)


def extract_content_from_html(html_str: str) -> ExtractedDocument:
    """
    Parses HTML, cleans noise, and segments readable body text into paragraphs.
    """
    if not html_str or not html_str.strip():
        return ExtractedDocument(title="", paragraphs=[], full_text="", word_count=0)

    soup = BeautifulSoup(html_str, "html.parser")

    # Extract title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Remove non-content tags
    for tag in soup.find_all(BOILERPLATE_TAGS):
        tag.decompose()

    # Remove elements matching noise patterns
    for tag in soup.find_all(attrs={"class": NOISE_PATTERN}):
        # Keep if it is a main article or body
        if tag.name not in ["article", "main"]:
            tag.decompose()

    for tag in soup.find_all(attrs={"id": NOISE_PATTERN}):
        if tag.name not in ["article", "main"]:
            tag.decompose()

    # Extract main content container if available
    content_root = soup.find("article") or soup.find("main") or soup.find(id=re.compile(r"content|article|main", re.I)) or soup.body or soup

    # Extract text blocks from meaningful block-level elements
    block_elements = content_root.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"])

    paragraphs: List[str] = []
    seen_hashes = set()

    for elem in block_elements:
        text = elem.get_text(separator=" ", strip=True)
        # Normalize excessive whitespace but preserve capitalization & punctuation
        text = re.sub(r"\s+", " ", text).strip()

        # Filter out short fragments, buttons, or repetitive noise
        if len(text) >= 25 and len(text.split()) >= 4:
            # Simple dedup for identical lines
            h = text.lower()
            if h not in seen_hashes:
                seen_hashes.add(h)
                paragraphs.append(text)

    # Fallback if no block elements were found (e.g. plain text or unusual markup)
    if not paragraphs:
        raw_text = content_root.get_text(separator="\n", strip=True)
        for line in raw_text.splitlines():
            line_clean = re.sub(r"\s+", " ", line).strip()
            if len(line_clean) >= 25 and len(line_clean.split()) >= 4:
                paragraphs.append(line_clean)

    full_text = "\n\n".join(paragraphs)
    word_count = len(full_text.split())

    return ExtractedDocument(
        title=title,
        paragraphs=paragraphs,
        full_text=full_text,
        word_count=word_count,
    )
