"""
Passage Selector and Relevance Scorer for Citation Binder.

Locates and ranks the most relevant passages from an extracted document
relative to the claim using token overlap, BM25 scoring, and entity matching.
"""

import math
import re
from typing import List, Set, Tuple
from pydantic import BaseModel, Field

# Common English stopwords
STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves"
}

TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9_\-']+\b")
NUMBER_PATTERN = re.compile(r"\b\d+(?:[\.,]\d+)?%?\b")


class Passage(BaseModel):
    index: int
    text: str
    relevance_score: float
    matched_terms: List[str] = Field(default_factory=list)


def tokenize(text: str) -> List[str]:
    """Tokenizes text into lowercase tokens."""
    return [t.lower() for t in TOKEN_PATTERN.findall(text)]


def extract_keywords(text: str) -> Tuple[List[str], List[str]]:
    """
    Extracts informative keywords and numeric tokens from text, excluding stopwords.
    """
    tokens = tokenize(text)
    keywords = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    numbers = NUMBER_PATTERN.findall(text)
    return keywords, numbers


def select_relevant_passages(
    claim: str,
    paragraphs: List[str],
    top_k: int = 4,
    min_score_threshold: float = 0.5,
) -> List[Passage]:
    """
    Ranks paragraphs based on BM25-style term weighting and numeric/entity overlap with the claim.
    Returns the top K candidate passages that meet the minimum relevance threshold.
    """
    if not claim or not paragraphs:
        return []

    claim_keywords, claim_numbers = extract_keywords(claim)
    if not claim_keywords and not claim_numbers:
        return []

    # Also build 2-paragraph sliding windows to catch thoughts spanning paragraph breaks
    windows = []
    for i, p in enumerate(paragraphs):
        windows.append((i, p))
        if i < len(paragraphs) - 1:
            combined = f"{p} {paragraphs[i+1]}"
            windows.append((i, combined))

    N = len(windows)
    avg_len = sum(len(tokenize(w[1])) for w in windows) / max(N, 1)

    # Document frequency for claim terms
    doc_freq = {}
    window_tokens_list = []
    for _, text in windows:
        toks = set(tokenize(text))
        window_tokens_list.append(toks)
        for kw in claim_keywords:
            if kw in toks:
                doc_freq[kw] = doc_freq.get(kw, 0) + 1

    # BM25 constants
    k1 = 1.5
    b = 0.75

    scored_passages: List[Passage] = []
    seen_texts: Set[str] = set()

    for idx, (orig_index, text) in enumerate(windows):
        text_clean = text.strip()
        if text_clean in seen_texts:
            continue
        seen_texts.add(text_clean)

        doc_tokens = tokenize(text)
        doc_len = len(doc_tokens)
        if doc_len == 0:
            continue

        doc_token_counts = {}
        for t in doc_tokens:
            doc_token_counts[t] = doc_token_counts.get(t, 0) + 1

        score = 0.0
        matched: List[str] = []

        # 1. BM25 term weighting
        for kw in claim_keywords:
            tf = doc_token_counts.get(kw, 0)
            if tf > 0:
                matched.append(kw)
                df = doc_freq.get(kw, 0)
                # BM25 IDF
                idf = math.log(1.0 + (N - df + 0.5) / (df + 0.5))
                # BM25 TF
                term_score = idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (doc_len / max(avg_len, 1)))))
                score += max(0.0, term_score)

        # 2. Strong bonus for matching numbers/dates/percentages
        for num in claim_numbers:
            if num in text:
                score += 2.0
                matched.append(num)

        # 3. Bonus for multi-word phrase matching
        claim_lower = claim.lower()
        if len(claim_keywords) >= 2:
            for i in range(len(claim_keywords) - 1):
                bigram = f"{claim_keywords[i]} {claim_keywords[i+1]}"
                if bigram in text.lower():
                    score += 1.5

        if score >= min_score_threshold:
            scored_passages.append(Passage(
                index=orig_index,
                text=text_clean,
                relevance_score=round(score, 3),
                matched_terms=list(set(matched))
            ))

    # Sort descending by score
    scored_passages.sort(key=lambda p: p.relevance_score, reverse=True)

    # Return top K unique passages
    top_passages: List[Passage] = []
    selected_texts: Set[str] = set()
    for p in scored_passages:
        # Avoid duplicating overlapping sub-passages
        is_subset = any(p.text in existing.text or existing.text in p.text for existing in top_passages)
        if not is_subset:
            top_passages.append(p)
            selected_texts.add(p.text)
        if len(top_passages) >= top_k:
            break

    return top_passages
