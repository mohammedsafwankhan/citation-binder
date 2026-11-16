"""
Configuration settings for Citation Binder.
"""

import os
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


class Settings:
    APP_NAME: str = "Citation Binder"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8080"))

    # Security & Retrieval Limits
    MAX_REDIRECTS: int = int(os.getenv("MAX_REDIRECTS", "5"))
    MAX_BODY_BYTES: int = int(os.getenv("MAX_BODY_BYTES", str(2 * 1024 * 1024)))  # 2MB
    FETCH_TIMEOUT: float = float(os.getenv("FETCH_TIMEOUT", "8.0"))

    # Assessment & Passage Selection
    TOP_K_PASSAGES: int = int(os.getenv("TOP_K_PASSAGES", "4"))
    MIN_RELEVANCE_SCORE: float = float(os.getenv("MIN_RELEVANCE_SCORE", "0.5"))

    # Model Provider & Credentials
    # Providers: "gemini", "openai", "heuristic"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # If true, allows offline heuristic analysis when credentials are not configured
    ALLOW_HEURISTIC_FALLBACK: bool = os.getenv("ALLOW_HEURISTIC_FALLBACK", "false").lower() == "true"


settings = Settings()
