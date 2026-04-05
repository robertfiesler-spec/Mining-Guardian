#!/usr/bin/env python3
# ============================================================
# ams_auth_test.py
# BiXBiT AMS — Authentication + WebSocket connection test
#
# Auth flow (discovered):
#   1. POST /auth/login            → JWT returned as COOKIE
#   2. POST /auth/select_workspace → workspace JWT as COOKIE
#   3. Connect to dashboard WebSocket using workspace token
#
# Usage:
#   source venv/bin/activate
#   python ams_auth_test.py
#
# Author: Rob Fiesler | BiXBiT USA
# ============================================================

import os, json, sys
import requests
import websocket

BASE_URL = "https://api-staging.dev.bixbit.io/api/v1"
WS_BASE  = "wss://api-staging.dev.bixbit.io/api/v1"
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def load_env(path):
    env = {}
    if not os.path.exists(path):
        print(f"[ERROR] .env not found. Run: cp .env.example .env")
        sys.exit(1)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def login(session, email, password):
    # Key discovery: JWT is NOT in the JSON body.
    # It comes back as an HTTP Set-Cookie header named "access_token".
    # requests.Session() stores it automatically for the next call.
    print(f"\n[1/3] Logging in as {email} ...")
    resp = session.post(f"{BASE_URL}/auth/login",
                        json={"email": email, "password": password}, timeout=15)
    if resp.status_code != 200:
        print(f"[ERROR] Login failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    token = session.cookies.get("access_token")
    if not token:
        print("[ERROR] No access_token cookie in login response.")
        sys.exit(1)
    print(f"  ✓ User token  [{token[:30]}...]")
    return token


def select_workspace(session, user_token, workspace_id):
    # Pass user token as Bearer. On success, server sets a NEW
    # access_token cookie scoped to this workspace — full permissions.
    print(f"[2/3] Selecting workspace {workspace_id} ...")
    resp = session.post(f"{BASE_URL}/auth/select_workspace",
                        json={"id": workspace_id},
                        headers={"Authorization": f"Bearer {user_token}"}, timeout=15)
    if resp.status_code != 200:
        print(f"[ERROR] select_workspace failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    ws_token = session.cookies.get("access_token")
    if not ws_token:
        print("[ERROR] No workspace token cookie in response.")
        sys.exit(1)
    print(f"  ✓ Workspace token  [{ws_token[:30]}...]")
    return ws_token


def test_dashboard_ws(ws_token):
    ws_url, received = f"{WS_BASE}/miners/dashboard_ws", []
    print(f"[3/3] Connecting to WebSocket ...\n      {ws_url}")

    def on_open(ws):   print("  ✓ Connected")
    def on_error(ws, e): print(f"  [WS ERROR] {e}")
    def on_close(ws, c, m): print(f"  Closed [status={c}]")
    def on_message(ws, msg):
        if not received:
            received.append(msg)
            print("\n  ✓ First message received:")
            try: print(json.dumps(json.loads(msg), indent=2))
            except: print(msg)
        ws.close()

    websocket.WebSocketApp(ws_url,
        header={"Authorization": f"Bearer {ws_token}"},
        subprotocols=[ws_token],
        on_open=on_open, on_message=on_message,
        on_error=on_error, on_close=on_close
    ).run_forever()

    if not received:
        print("\n  [WARN] No message received — may need different WS endpoint.")


def main():
    env = load_env(ENV_FILE)
    email, password = env.get("AMS_EMAIL"), env.get("AMS_PASSWORD")
    workspace_id = env.get("AMS_WORKSPACE_ID")
    if not all([email, password, workspace_id]):
        print("[ERROR] .env missing: AMS_EMAIL, AMS_PASSWORD, AMS_WORKSPACE_ID")
        sys.exit(1)
    try: workspace_id = int(workspace_id)
    except ValueError:
        print("[ERROR] AMS_WORKSPACE_ID must be an integer"); sys.exit(1)

    print("=" * 44)
    print("  BiXBiT AMS — Auth + WebSocket Test")
    print("=" * 44)

    session    = requests.Session()
    user_token = login(session, email, password)
    ws_token   = select_workspace(session, user_token, workspace_id)
    test_dashboard_ws(ws_token)

    print("\n" + "=" * 44 + "\n  Done.\n" + "=" * 44)


if __name__ == "__main__":
    main()
