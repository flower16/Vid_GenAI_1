"""
Unified integration status for the platform's external services.

One place to answer "is X wired, and can we reach it right now?" for Snowflake,
LangSmith, Fireworks, Azure AD, and Pinecone. Every service is optional — the
platform runs fully locally without any of them — so this module never raises:
a missing key reports `configured=False`, and a live-check failure reports
`reachable=False` with the reason.

Used by the `/api/v1/health/integrations` route and `scripts/check_integrations.py`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from .config import settings

_PING_TIMEOUT_S = 6


@dataclass
class IntegrationStatus:
    name: str
    configured: bool
    reachable: Optional[bool]  # None when not live-checked (or not configured)
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _http_ok(url: str, headers: dict | None = None) -> tuple[bool, str]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_PING_TIMEOUT_S) as resp:
            return (200 <= resp.status < 300), f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        # A 401/403 still proves the endpoint is reachable and the host is up.
        return (e.code in (401, 403)), f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, str(e)[:200]


# --------------------------------------------------------------------------- #
# Per-service checks. Each returns IntegrationStatus. `live` toggles the ping.
# --------------------------------------------------------------------------- #
def check_langsmith(live: bool) -> IntegrationStatus:
    configured = bool(settings.langsmith_api_key)
    st = IntegrationStatus("langsmith", configured, None,
                           f"project={settings.langsmith_project}, "
                           f"tracing={'on' if settings.langsmith_tracing else 'off'}")
    if configured and live:
        try:
            from langsmith import Client
            next(iter(Client().list_datasets(limit=1)), None)
            st.reachable, st.detail = True, st.detail + "; API reachable"
        except Exception as e:  # noqa: BLE001 - report, never raise
            st.reachable, st.detail = False, st.detail + f"; {type(e).__name__}: {str(e)[:160]}"
    return st


def check_fireworks(live: bool) -> IntegrationStatus:
    configured = bool(settings.fireworks_api_key)
    st = IntegrationStatus("fireworks", configured, None,
                           f"judge_model={settings.fireworks_judge_model}")
    if configured and live:
        ok, detail = _http_ok(f"{settings.fireworks_base_url}/models",
                              {"Authorization": f"Bearer {settings.fireworks_api_key}"})
        st.reachable, st.detail = ok, st.detail + f"; {detail}"
    return st


def check_snowflake(live: bool) -> IntegrationStatus:
    configured = bool(settings.snowflake_account and settings.snowflake_user
                      and settings.snowflake_password)
    st = IntegrationStatus("snowflake", configured, None,
                           f"db={settings.snowflake_database}.{settings.snowflake_schema}")
    if configured and live:
        try:
            import snowflake.connector
            conn = snowflake.connector.connect(
                account=settings.snowflake_account, user=settings.snowflake_user,
                password=settings.snowflake_password,
                warehouse=settings.snowflake_warehouse or None,
                role=settings.snowflake_role or None,
                database=settings.snowflake_database, schema=settings.snowflake_schema,
                login_timeout=_PING_TIMEOUT_S)
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            conn.close()
            st.reachable, st.detail = True, st.detail + "; SELECT 1 ok"
        except Exception as e:  # noqa: BLE001
            st.reachable, st.detail = False, st.detail + f"; {type(e).__name__}: {str(e)[:160]}"
    return st


def check_azure_ad(live: bool) -> IntegrationStatus:
    configured = bool(settings.azure_tenant_id and settings.azure_client_id)
    tenant = settings.azure_tenant_id or "common"
    st = IntegrationStatus("azure_ad", configured, None, f"tenant={tenant}")
    if configured and live:
        ok, detail = _http_ok(
            f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration")
        st.reachable, st.detail = ok, st.detail + f"; OIDC metadata {detail}"
    return st


def check_pinecone(live: bool) -> IntegrationStatus:
    configured = bool(settings.pinecone_api_key)
    st = IntegrationStatus("pinecone", configured, None, f"index={settings.pinecone_index}")
    if configured and live:
        try:
            from pinecone import Pinecone
            names = [i["name"] for i in Pinecone(api_key=settings.pinecone_api_key).list_indexes()]
            present = settings.pinecone_index in names
            st.reachable = True
            st.detail += f"; index_present={present}"
        except Exception as e:  # noqa: BLE001
            st.reachable, st.detail = False, st.detail + f"; {type(e).__name__}: {str(e)[:160]}"
    return st


_CHECKS: list[Callable[[bool], IntegrationStatus]] = [
    check_langsmith, check_fireworks, check_snowflake, check_azure_ad, check_pinecone,
]


def integration_report(live: bool = False) -> dict:
    """Full status for every integration.

    `live=False` (default) only reports whether each is configured — cheap and
    safe for a frequently-polled health endpoint. `live=True` also pings each
    configured service.
    """
    statuses = [c(live) for c in _CHECKS]
    return {
        "environment": settings.environment,
        "live_checked": live,
        "configured_count": sum(s.configured for s in statuses),
        "integrations": [s.to_dict() for s in statuses],
    }
