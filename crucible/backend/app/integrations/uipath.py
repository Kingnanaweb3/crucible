"""UiPath Test Manager connectivity client for Crucible.

Auth: OAuth2 client-credentials via a registered External Application. The Test
Manager REST API does NOT accept a Personal Access Token, so client credentials
are the real path. Falls back to the PAT only if no client creds are set.

Run from backend/:  python -m app.integrations.uipath
"""

from __future__ import annotations

import sys

import httpx

from app.config import settings


def _org_base() -> str:
    return f"{settings.uipath_base_url.rstrip('/')}/{settings.uipath_org}"


def _tm_base() -> str:
    return f"{_org_base()}/{settings.uipath_tenant}/testmanager_"


def get_token() -> tuple[str, str]:
    """Returns (token, auth_method)."""
    if settings.uipath_client_id and settings.uipath_client_secret:
        url = f"{_org_base()}/identity_/connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": settings.uipath_client_id,
            "client_secret": settings.uipath_client_secret,
        }
        if settings.uipath_scopes:
            data["scope"] = settings.uipath_scopes
        resp = httpx.post(url, data=data, timeout=30.0)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Token request failed: HTTP {resp.status_code} - {resp.text[:300]}"
            )
        return resp.json()["access_token"], "client-credentials"
    if settings.uipath_pat:
        return settings.uipath_pat, "PAT"
    raise RuntimeError("Set UIPATH_CLIENT_ID/SECRET (preferred) or UIPATH_PAT in .env")


def list_projects(token: str) -> httpx.Response:
    url = f"{_tm_base()}/api/v2/projects"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return httpx.get(url, headers=headers, timeout=30.0)


def main() -> None:
    print("Crucible -> UiPath Test Manager connectivity check")
    print("-" * 50)
    print(f"Base: {_tm_base()}")

    try:
        token, method = get_token()
        print(f"Auth: token acquired via {method}")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] auth: {exc}")
        sys.exit(1)

    try:
        resp = list_projects(token)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] request error: {type(exc).__name__}: {exc}")
        sys.exit(1)

    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        try:
            data = resp.json()
        except Exception:
            print(resp.text[:500])
            return
        projects = data if isinstance(data, list) else (
            data.get("items") or data.get("value") or data.get("data") or []
        )
        names = (
            [p.get("name") or p.get("Name") for p in projects]
            if isinstance(projects, list)
            else []
        )
        print(f"Projects found: {names}")
        if any((n or "").lower() == "crucible" for n in names):
            print("[PASS] 'Crucible' found - decision gate cleared.")
        else:
            print("[warn] Connected, but 'Crucible' not in list. Check tenant/project.")
    else:
        print(resp.text[:500])


if __name__ == "__main__":
    main()
