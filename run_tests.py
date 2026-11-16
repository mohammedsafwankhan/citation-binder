"""
Automated test runner for Citation Binder.
Executes all unit and integration test suites directly.
"""

import asyncio
import sys
from tests.test_ssrf import (
    test_public_ip_allowed,
    test_private_ips_blocked,
    test_url_scheme_validation,
    test_credentials_in_url_blocked,
    test_localhost_and_cloud_metadata_blocked,
    test_dns_resolution_failure_is_distinct_from_ssrf,
)
from tests.test_extractor import (
    test_extract_content_and_clean_boilerplate,
    test_extract_empty_or_malformed,
)
from tests.test_fetcher import (
    test_retrieve_html_document,
    test_retrieve_pdf_document,
    test_reject_unsupported_content_type,
    test_reject_oversized_response,
    test_reject_empty_text,
    test_timeout_handling,
    test_reject_unsafe_redirect_hop,
)
from tests.test_evaluator import (
    get_sample_source_text,
    test_verdict_supports,
    test_verdict_does_not_support,
    test_verdict_partially_supports,
    test_verdict_unable_to_verify_when_evidence_missing,
    test_quote_verification_ground_truth,
    test_missing_credentials_shows_setup_message,
    test_invalid_model_response_returns_unable_to_verify,
    test_never_claim_support_without_source_evidence,
    test_never_claim_partial_support_without_source_evidence,
)
from tests.test_api import (
    test_health_endpoint,
    test_ssrf_blocking_in_api,
    test_standalone_retrieve_endpoint,
    test_successful_verification_flow,
)


def run_all_tests():
    passed = 0
    failed = 0
    errors = []

    sync_tests = [
        ("SSRF: Public IP Allowed", test_public_ip_allowed, ()),
        ("SSRF: Private & Metadata IPs Blocked", test_private_ips_blocked, ()),
        ("SSRF: URL Scheme Validation", test_url_scheme_validation, ()),
        ("SSRF: URL Credentials Blocked", test_credentials_in_url_blocked, ()),
        ("SSRF: Localhost & Metadata Blocked", test_localhost_and_cloud_metadata_blocked, ()),
        ("SSRF: DNS Failure is Distinct from Attack", test_dns_resolution_failure_is_distinct_from_ssrf, ()),
        ("Extractor: Clean Boilerplate", test_extract_content_and_clean_boilerplate, ()),
        ("Extractor: Empty & Malformed HTML", test_extract_empty_or_malformed, ()),
    ]

    sample_text = get_sample_source_text()
    evaluator_tests = [
        ("Evaluator: Verdict SUPPORTS", test_verdict_supports, (sample_text,)),
        ("Evaluator: Verdict DOES_NOT_SUPPORT", test_verdict_does_not_support, (sample_text,)),
        ("Evaluator: Verdict PARTIALLY_SUPPORTS", test_verdict_partially_supports, (sample_text,)),
        ("Evaluator: Verdict UNABLE_TO_VERIFY", test_verdict_unable_to_verify_when_evidence_missing, (sample_text,)),
        ("Evaluator: Ground-truth Quote Verification", test_quote_verification_ground_truth, (sample_text,)),
    ]

    async_tests = [
        ("Retrieval: HTML Document Parsing", test_retrieve_html_document, ()),
        ("Retrieval: PDF Support & Validation", test_retrieve_pdf_document, ()),
        ("Retrieval: Unsupported Content Type Rejected", test_reject_unsupported_content_type, ()),
        ("Retrieval: Oversized Response Streaming Abort", test_reject_oversized_response, ()),
        ("Retrieval: Empty Text Content Rejected", test_reject_empty_text, ()),
        ("Retrieval: Network Timeout Handling", test_timeout_handling, ()),
        ("Retrieval: Unsafe Redirect Hop Blocked", test_reject_unsafe_redirect_hop, ()),
        ("Evaluator: Missing Credentials Setup Notice", test_missing_credentials_shows_setup_message, (sample_text,)),
        ("Evaluator: Invalid Model Response Handling", test_invalid_model_response_returns_unable_to_verify, (sample_text,)),
        ("Evaluator: No Support Without Ground Truth", test_never_claim_support_without_source_evidence, (sample_text,)),
        ("Evaluator: No Partial Support Without Evidence", test_never_claim_partial_support_without_source_evidence, (sample_text,)),
        ("API: Health Check Endpoint", test_health_endpoint, ()),
        ("API: SSRF Security Blocking", test_ssrf_blocking_in_api, ()),
        ("API: Standalone Retrieval Endpoint", test_standalone_retrieve_endpoint, ()),
        ("API: End-to-End Verification Flow", test_successful_verification_flow, ()),
    ]

    print("==================================================")
    print("      Running Citation Binder Test Suite          ")
    print("==================================================")

    for name, fn, args in sync_tests + evaluator_tests:
        try:
            fn(*args)
            print(f" [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f" [FAIL] {name}: {e}")
            failed += 1
            errors.append((name, str(e)))

    for name, fn, args in async_tests:
        try:
            asyncio.run(fn(*args))
            print(f" [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f" [FAIL] {name}: {e}")
            failed += 1
            errors.append((name, str(e)))

    print("--------------------------------------------------")
    print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
    print("==================================================")

    if failed > 0:
        for name, err in errors:
            print(f"FAILED: {name} -> {err}")
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
