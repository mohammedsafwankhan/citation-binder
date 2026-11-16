# Security Policy

## Threat Model & Invariants

Citation Binder is engineered to serve as a high-integrity, defensive security barrier for AI applications, autonomous agents, and RAG pipelines.

We enforce the following core invariants:
1. **Network Boundary Isolation**: The retrieval layer performs strict pre-flight DNS filtering. Private IPv4/IPv6 ranges (RFC 1918), loopback (`127.0.0.0/8`), carrier-grade NAT (`100.64.0.0/10`), link-local, and cloud metadata endpoints (`169.254.169.254`) are rejected before socket establishment.
2. **Hop-by-Hop Redirect Verification**: Each intermediate HTTP redirect target is re-validated against the SSRF guard (up to 5 hops maximum).
3. **DoS & Resource Exhaustion Protection**: Response bodies are streamed in 16KB chunks and aborted if total content exceeds 2 MB. Network requests time out strictly after 8 seconds.
4. **Untrusted Input Demarcation**: Fetched third-party web content is tagged with `is_untrusted_data=True` and isolated inside `<untrusted_source_passage>` XML tags to resist indirect prompt injection (OWASP LLM01).
5. **Zero-Hallucination Gate**: No positive verification verdict (`supports` or `partially supports`) can be returned without authentic, verbatim substring quotes verified to exist in the source document.

## Reporting a Vulnerability

If you discover a security vulnerability within Citation Binder:
- **Do not open a public issue.**
- Please email the maintainers or report via GitHub Security Advisories.
- Include reproduction steps, a proof of concept (PoC), and affected versions.

We appreciate responsible disclosure and aim to acknowledge valid reports within 24 hours.
