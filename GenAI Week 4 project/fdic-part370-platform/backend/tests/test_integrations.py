"""Integration status layer — structure + graceful behavior (no network)."""

from app.core.integrations import integration_report

_NAMES = {"langsmith", "fireworks", "snowflake", "azure_ad", "pinecone"}


def test_report_lists_all_integrations_without_network():
    report = integration_report(live=False)
    assert {s["name"] for s in report["integrations"]} == _NAMES
    assert report["live_checked"] is False
    # Non-live reports never probe, so reachable is always unknown (None).
    for s in report["integrations"]:
        assert s["reachable"] is None
        assert isinstance(s["configured"], bool)
        assert set(s) == {"name", "configured", "reachable", "detail"}
    assert report["configured_count"] == sum(s["configured"] for s in report["integrations"])
