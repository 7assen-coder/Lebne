#!/usr/bin/env python3
"""Fetch a Keycloak access token for the local lebne realm (password grant)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--realm", default="lebne")
    parser.add_argument("--client-id", default="lebne-api")
    parser.add_argument("--username", default="demo")
    parser.add_argument("--password", default="DemoPass123!")
    args = parser.parse_args()

    url = f"{args.base}/realms/{args.realm}/protocol/openid-connect/token"
    data = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": args.client_id,
            "username": args.username,
            "password": args.password,
        }
    ).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        print(f"Keycloak token request failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(payload["access_token"])


if __name__ == "__main__":
    main()
