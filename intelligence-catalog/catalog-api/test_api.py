"""
Test script for the Catalog API.

Usage:
    python test_api.py [--base-url URL] [--api-key KEY]

Hits all three endpoints and prints results. Designed to run against a live
instance — start the API first with `docker-compose up` or `uvicorn`.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

DEFAULT_BASE_URL = "http://localhost:8420"
# CRIT-6: there is no working default. Pass --api-key from your installed .env
# or set the CATALOG_API_KEY env var; the placeholder string is rejected
# by the server at startup.
DEFAULT_API_KEY = os.environ.get("CATALOG_API_KEY", "")


def _request(method: str, url: str, api_key: str, body: dict | None = None) -> tuple[int, dict]:
    """Make an HTTP request and return (status_code, response_json)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode() if exc.fp else ""
        try:
            return exc.code, json.loads(body_text)
        except json.JSONDecodeError:
            return exc.code, {"raw": body_text}
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc.reason)}


def test_health(base_url: str, api_key: str) -> bool:
    """Test GET /api/v1/health."""
    print("\n--- Test: GET /api/v1/health ---")
    status, data = _request("GET", f"{base_url}/api/v1/health", api_key)
    print(f"Status: {status}")
    print(json.dumps(data, indent=2, default=str))
    ok = status == 200 and data.get("status") in ("healthy", "degraded")
    print(f"Result: {'PASS' if ok else 'FAIL'}")
    return ok


def test_scan_bundle(base_url: str, api_key: str) -> bool:
    """Test POST /api/v1/context/scan-bundle."""
    print("\n--- Test: POST /api/v1/context/scan-bundle ---")
    payload = {
        "miner_models": ["Antminer S19j Pro", "Antminer S19 XP"],
        "active_issues": ["RESTART", "TEMP_ACTION_REQUIRED"],
        "chip_dies": ["BM1362AA", "BM1366"],
        "firmware_versions": ["19.10.0", "22.08.30"],
        "include_sections": ["failure_patterns", "firmware", "thresholds", "repair", "env_factors", "baselines"],
    }
    status, data = _request("POST", f"{base_url}/api/v1/context/scan-bundle", api_key, payload)
    print(f"Status: {status}")
    if status == 200:
        print(f"Cache key: {data.get('cache_key')}")
        print(f"Generated at: {data.get('generated_at')}")
        print(f"Sources: {data.get('sources')}")
        print(f"Prompt text length: {len(data.get('prompt_text', ''))} chars")
        print(f"Bundle keys: {list(data.get('context_bundle', {}).keys())}")
        # Print truncated prompt text
        prompt = data.get("prompt_text", "")
        if prompt:
            print(f"\n--- Prompt text (first 500 chars) ---\n{prompt[:500]}")
    else:
        print(json.dumps(data, indent=2, default=str))
    ok = status == 200 and "context_bundle" in data
    print(f"\nResult: {'PASS' if ok else 'FAIL'}")
    return ok


def test_miner_knowledge(base_url: str, api_key: str) -> bool:
    """Test GET /api/v1/knowledge/miner/{model_slug}."""
    print("\n--- Test: GET /api/v1/knowledge/miner/antminer-s19j-pro ---")
    status, data = _request(
        "GET",
        f"{base_url}/api/v1/knowledge/miner/antminer-s19j-pro?include=specs,firmware,failures,repair,thresholds",
        api_key,
    )
    print(f"Status: {status}")
    if status == 200:
        model = data.get("model", {})
        print(f"Model: {model.get('model_name', 'N/A')}")
        print(f"Response keys: {list(data.keys())}")
    else:
        print(json.dumps(data, indent=2, default=str))
    ok = status in (200, 404)  # 404 is ok if model not seeded yet
    print(f"Result: {'PASS' if ok else 'FAIL'}")
    return ok


def test_auth_rejection(base_url: str) -> bool:
    """Test that requests without valid auth are rejected."""
    print("\n--- Test: Auth rejection (no token) ---")
    status, data = _request("POST", f"{base_url}/api/v1/context/scan-bundle", "WRONG_KEY", {"miner_models": []})
    print(f"Status: {status}")
    ok = status == 403
    print(f"Result: {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    """Run all tests against a live Catalog API instance."""
    parser = argparse.ArgumentParser(description="Test the Catalog API")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Bearer token")
    args = parser.parse_args()

    print(f"Testing Catalog API at {args.base_url}")
    print("=" * 60)

    results = [
        test_health(args.base_url, args.api_key),
        test_scan_bundle(args.base_url, args.api_key),
        test_miner_knowledge(args.base_url, args.api_key),
        test_auth_rejection(args.base_url),
    ]

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    if passed == total:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
