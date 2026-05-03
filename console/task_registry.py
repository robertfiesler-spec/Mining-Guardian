"""
console/task_registry.py — D-19 task registry view

The 11 scheduled tasks per the D-18 launchd transition (replaces the legacy
setup.sh phase_10 cron block). Each entry maps a stable `task_key` (used as
the URL slug and DB key) to the launchd label, human-friendly name, default
schedule, and a short description.

This file is the single-source-of-truth for the registry. The console
renders it on /tasks; future work on Gap 4 (scheduled-tasks launchd plists
under installer/macos-pkg/resources/launchd/scheduled/) will read the same
list to generate plists, ensuring the UI and the install matrix never
disagree.

Status / running / paused / last-run / next-run / last-result are NOT
hard-coded here. They come from runtime sources at request time:
  - Service plists (the 9 daemons): launchctl print system/<label>
    + system_schedules table for poll/window jobs.
  - Scheduled jobs (the 11 cron-replacement plists from Gap 4): plist
    StartCalendarInterval + last-run timestamp from the job's stamp file
    or from system_settings (last_run_<task_key>).

In v1 of the console, `last_result` and `next_run` are best-effort and
may render "—" if the underlying source is not yet wired. The structure
is in place so Gap 4 can light it up without further UI work.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TaskDefinition:
    task_key: str            # stable slug, e.g. "morning_briefing"
    name: str                # operator-facing name, e.g. "Morning Briefing"
    category: str            # "service" | "scheduled" | "poll"
    plist_label: Optional[str]  # launchd label, None for in-process polls
    default_schedule: str    # human-readable, e.g. "07:00 daily"
    description: str         # 1-line operator-facing description
    pausable: bool           # whether the toggle is exposed in v1
    schedule_editable: bool  # whether time-edit is exposed in v1


# Order is the order rendered in the UI. Categories are grouped.
TASK_REGISTRY: List[TaskDefinition] = [
    # ── Always-on services (the 9 LaunchDaemons from Bucket 6) ──
    TaskDefinition(
        task_key="scanner",
        name="Hourly Scanner",
        category="service",
        plist_label="com.miningguardian.scanner",
        default_schedule="every 60 min (KeepAlive)",
        description="Polls all miners, runs the 8 AI features, writes scan rows.",
        pausable=True,
        schedule_editable=False,
    ),
    TaskDefinition(
        task_key="dashboard_api",
        name="Dashboard API",
        category="service",
        plist_label="com.miningguardian.dashboard-api",
        default_schedule="continuous (KeepAlive)",
        description="FastAPI on :8585 — Prometheus, Retool, Grafana iframes.",
        pausable=False,
        schedule_editable=False,
    ),
    TaskDefinition(
        task_key="approval_api",
        name="Approval API",
        category="service",
        plist_label="com.miningguardian.approval-api",
        default_schedule="continuous (KeepAlive)",
        description="FastAPI on :8686 — Slack approve/deny + existing /ui GUI.",
        pausable=False,
        schedule_editable=False,
    ),
    TaskDefinition(
        task_key="slack_listener",
        name="Slack Socket Listener",
        category="service",
        plist_label="com.miningguardian.slack-listener",
        default_schedule="continuous (KeepAlive)",
        description="Slack Socket Mode consumer (outbound only).",
        pausable=True,
        schedule_editable=False,
    ),
    TaskDefinition(
        task_key="slack_commands",
        name="Slack Commands",
        category="service",
        plist_label="com.miningguardian.slack-commands",
        default_schedule="continuous (KeepAlive)",
        description="Slack slash-command handler.",
        pausable=True,
        schedule_editable=False,
    ),
    TaskDefinition(
        task_key="overnight_automation",
        name="Overnight Automation",
        category="service",
        plist_label="com.miningguardian.overnight-automation",
        default_schedule="22:00–06:00 window",
        description="Auto-approves AUTO-classified actions during the overnight window.",
        pausable=True,
        schedule_editable=True,  # window edit via system_schedules.overnight_window
    ),
    TaskDefinition(
        task_key="alerts",
        name="AMS Alerts Listener",
        category="service",
        plist_label="com.miningguardian.alerts",
        default_schedule="continuous (KeepAlive)",
        description="Polls AMS alert stream for fault events.",
        pausable=True,
        schedule_editable=False,
    ),
    TaskDefinition(
        task_key="intelligence_report",
        name="Intelligence Report API",
        category="service",
        plist_label="com.miningguardian.intelligence-report",
        default_schedule="continuous (KeepAlive)",
        description="FastAPI for catalog-backed intelligence reports.",
        pausable=False,
        schedule_editable=False,
    ),
    TaskDefinition(
        task_key="feedback_loop",
        name="Feedback Loop Daemon",
        category="service",
        plist_label="com.miningguardian.feedback-loop-daemon",
        default_schedule="continuous (KeepAlive)",
        description="Catalog feedback-loop daemon (D-14).",
        pausable=True,
        schedule_editable=False,
    ),

    # ── Scheduled jobs (Gap 4 will land plists for these) ──
    TaskDefinition(
        task_key="db_maintenance",
        name="DB Maintenance",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.db-maintenance",
        default_schedule="03:30 daily",
        description="WAL checkpoint, vacuum, integrity check.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="knowledge_backup",
        name="Knowledge Backup",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.knowledge-backup",
        default_schedule="04:00 daily",
        description="Backup knowledge.json to /Library/Application Support/MiningGuardian/backups/.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="morning_briefing",
        name="Morning Briefing",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.morning-briefing",
        default_schedule="07:00 daily",
        description="Daily summary posted to Slack.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="operator_review",
        name="Daily Operator Review",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.operator-review",
        default_schedule="08:00 daily",
        description="Generates the daily operator review report.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="ams_cleanup",
        name="AMS Log Cleanup",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.ams-cleanup",
        default_schedule="12:45 daily",
        description="Clears AMS-side logs 15 min before direct collection.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="log_collection",
        name="Direct Log Collection",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.log-collection",
        default_schedule="13:00 daily",
        description="Pulls logs directly from miners.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="daily_deep_dive",
        name="Daily Deep Dive (Qwen)",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.daily-deep-dive",
        default_schedule="16:00 daily",
        description="Local LLM analyzes each miner — Pass 1 of weekly chain.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="log_failure_report",
        name="Log Failure Report",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.log-failure-report",
        default_schedule="16:15 daily",
        description="Reports failed log collections from the 13:00 run.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="benchmark",
        name="Hourly Benchmark",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.benchmark",
        default_schedule="hourly",
        description="Performance tracking sample.",
        pausable=True,
        schedule_editable=True,
    ),
    TaskDefinition(
        task_key="weekly_training",
        name="Weekly Claude Training",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.weekly-training",
        default_schedule="Sunday — see CRON_SCHEDULE.md",
        description="Sunday cohort training pass; refinement chain runs after.",
        pausable=True,
        schedule_editable=True,
    ),
    # D-18 Gap 4 / P-007 — refinement_chain was a separate cron entry in
    # the legacy schedule (`0 1 * * *` per docs/CRON_SCHEDULE.md row "Pass
    # 3+4 - Qwen reflection + Claude merge (1 AM)"). The P-006 console
    # foundation bundled it into weekly_training's description; this row
    # restores it as its own task so the operator can see Pass 3+4 status
    # independently of Pass 2.
    TaskDefinition(
        task_key="refinement_chain",
        name="Refinement Chain (Qwen + Claude)",
        category="scheduled",
        plist_label="com.miningguardian.scheduled.refinement-chain",
        default_schedule="01:00 daily",
        description="Pass 3 (Qwen reflection) + Pass 4 (Claude merge) of the learning chain.",
        pausable=True,
        schedule_editable=True,
    ),
]


def get_task(task_key: str) -> Optional[TaskDefinition]:
    """Return the TaskDefinition for a key, or None if unknown."""
    for t in TASK_REGISTRY:
        if t.task_key == task_key:
            return t
    return None


def task_keys() -> List[str]:
    return [t.task_key for t in TASK_REGISTRY]


def as_dicts() -> List[Dict]:
    """Return registry as plain dicts (for JSON / Jinja convenience)."""
    return [asdict(t) for t in TASK_REGISTRY]
