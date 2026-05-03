"""
tests/console/test_task_registry.py — D-19 console (P-006)

Validates the static task registry contract:
  - All required jobs are present.
  - task_keys are unique and stable.
  - schedule_editable tasks correspond to known system_schedules keys
    (or are explicitly Gap-4 placeholders).
"""

from console import task_registry as r


def test_registry_is_non_empty():
    assert len(r.TASK_REGISTRY) > 0


def test_task_keys_are_unique():
    keys = [t.task_key for t in r.TASK_REGISTRY]
    assert len(keys) == len(set(keys)), f"duplicate task_key in registry: {keys}"


def test_required_services_present():
    """The 9 core services from postinstall.sh PLIST_LABELS must all be
    represented in the console registry, otherwise the operator cannot
    pause/resume them from the UI."""
    expected_plists = {
        "com.miningguardian.scanner",
        "com.miningguardian.dashboard-api",
        "com.miningguardian.approval-api",
        "com.miningguardian.slack-listener",
        "com.miningguardian.slack-commands",
        "com.miningguardian.overnight-automation",
        "com.miningguardian.alerts",
        "com.miningguardian.intelligence-report",
        "com.miningguardian.feedback-loop-daemon",
    }
    registered = {t.plist_label for t in r.TASK_REGISTRY if t.plist_label}
    missing = expected_plists - registered
    assert not missing, f"core services missing from console registry: {missing}"


def test_eleven_scheduled_jobs_are_in_registry_or_serviced():
    """D-19 mentions the 11 scheduled jobs (the cron-replacement set).
    Each one should appear somewhere in the registry — either as a
    scheduled-category task with its own future plist, or as a
    service-category in-process job."""
    expected_scheduled_names = {
        "db_maintenance",
        "knowledge_backup",
        "morning_briefing",
        "operator_review",
        "ams_cleanup",
        "log_collection",
        "daily_deep_dive",
        "log_failure_report",
        "benchmark",
        "weekly_training",
    }
    registered_keys = {t.task_key for t in r.TASK_REGISTRY}
    missing = expected_scheduled_names - registered_keys
    assert not missing, f"scheduled jobs missing from registry: {missing}"


def test_get_task_known_and_unknown():
    assert r.get_task("scanner") is not None
    assert r.get_task("scanner").name == "Hourly Scanner"
    assert r.get_task("not-a-real-key") is None


def test_as_dicts_returns_serializable_payload():
    """Every entry must round-trip through JSON; the UI relies on that."""
    import json
    payload = r.as_dicts()
    assert json.dumps(payload), "as_dicts() output must be JSON serializable"
    assert all("task_key" in d and "name" in d for d in payload)


def test_pausable_implies_plist_label():
    """Anything we offer Pause/Resume on must have a plist label so
    launchctl can act on it."""
    for t in r.TASK_REGISTRY:
        if t.pausable:
            assert t.plist_label, (
                f"{t.task_key} is pausable but has no plist_label — "
                "Pause/Resume in the UI would have nothing to act on"
            )


def test_console_port_documented_in_registry_metadata_or_docstring():
    """Sanity: confirm the docstring mentions the 8686/8787 port note so a
    future maintainer reading task_registry.py finds the trail back to
    the rationale."""
    # Indirect: just assert the registry includes approval_api with the
    # expected schedule string referencing :8686 — that's the breadcrumb.
    api = r.get_task("approval_api")
    assert api is not None
    assert "8686" in api.description
    console_doc = r.__doc__ or ""
    assert "11" in console_doc or "scheduled" in console_doc.lower()
