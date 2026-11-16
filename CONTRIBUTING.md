# Contributing to Citation Binder

Thank you for your interest in contributing to **Citation Binder**! We welcome contributions to help improve AI safety, citation fidelity, and autonomous verification tooling.

---

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mohammedsafwankhan/citation-binder.git
   cd citation-binder
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env if you wish to configure GEMINI_API_KEY or OPENAI_API_KEY
   ```

---

## Running Tests

Citation Binder maintains a 100% test pass rate across all security, extraction, retrieval, and evaluation modules.

Execute the test suite locally:
```bash
python run_tests.py
```

Or using pytest:
```bash
pytest tests/ -v
```

---

## Code Quality & Guidelines

- **Zero-Hallucination Invariant**: Any changes to claim evaluation must preserve the mechanical substring quote verification requirement. Positive verdicts must never be granted without verbatim corroboration.
- **SSRF Safety**: Never bypass or loosen IP/DNS validation boundaries in `app/services/ssrf_guard.py`.
- **Typing & Validation**: Use Pydantic schemas for all external inputs and outputs.
- **Formatting**: Adhere to PEP 8.

---

## Pull Request Process

1. Fork the repo and create your branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Write clean, documented code and add unit tests for new functionality.
3. Verify that all 28 tests pass (`python run_tests.py`).
4. Commit your changes with descriptive commit messages.
5. Push to your fork and submit a Pull Request describing your changes.
