#!/usr/bin/env python3
"""
Cleanup ALL AMS log files daily.

Since logs are stored in guardian.db after download, we don't need to keep
them in AMS. This prevents "too many log files" errors and keeps AMS clean.

LAUNCHD SCHEDULE (Mac Mini, D-18 Gap 4 / P-007):
    /Library/LaunchDaemons/com.miningguardian.scheduled.ams-cleanup.plist
    StartCalendarInterval Hour=10  # 10am daily - clean before 1pm log collection

LEGACY CRON (no longer used; kept for historical context):
    0 10 * * *  # 10am daily

OPERATOR REQUIREMENT (April 12 2026):
"Delete all files not just failed attempts. For clean up and house cleaning 
overall don't let it clutter. We store the logs in the db anyway."

P-038 item #7 (2026-05-11) -- path resolution.
Pre-P-038 this script hard-coded a legacy Linux dev path for both
`sys.path.insert` and the `GuardianConfig.from_file` argument. That
path does not exist on the Mac Mini install
(`/Library/Application Support/MiningGuardian/...`) so every scheduled
run crashed with `FileNotFoundError` against the legacy config path
and the launchd stamp recorded `exit_code=1` (5+ consecutive days,
May 6 -> May 10, 2026). Same fix-shape as P-034: resolve via
`_ROOT = Path(__file__).resolve().parent.parent` so the script works
under both the dev clone and the installed tree, and honor
`GUARDIAN_CONFIG` env var so an operator override works the same way
it does for `core/mining_guardian.py::__main__`. The static
regression test in `tests/test_p038_ams_cleanup_path_resolution.py`
forbids the legacy literal from ever reappearing in this file -- not
even in a docstring -- because a future "uncomment to test" mistake
would silently reintroduce the bug.
"""
import os
import sys
import time
import logging
from pathlib import Path

# P-038 item #7 (2026-05-11) -- compute _ROOT from this file's location
# instead of hard-coding a legacy Linux dev path. Matches the canonical
# idiom used in core/mining_guardian.py and scripts/daily_log_failure_report.py.
# On the Mac Mini install this resolves to
#   /Library/Application Support/MiningGuardian
# i.e. the parent of `scripts/`, which is ${MG_INSTALL_ROOT}. On the dev
# clone it resolves to the repo root.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.mining_guardian import AMSClient, GuardianConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def _resolve_config_path() -> str:
    """Return the config.json path for this run.

    Resolution order matches `core/mining_guardian.py::__main__`:
      1. `GUARDIAN_CONFIG` env var (explicit operator override).
      2. `_ROOT / "config.json"` (works under both dev clone and
         Mac Mini install tree).

    P-038 item #7. Returns a str rather than a Path because
    `GuardianConfig.from_file` is typed for str input.
    """
    explicit = os.environ.get("GUARDIAN_CONFIG")
    if explicit:
        return explicit
    return str(_ROOT / "config.json")


def cleanup_all_logs():
    """Delete ALL log files from AMS for all miners."""
    
    logger.info('=== AMS LOG CLEANUP START ===')
    
    config_path = _resolve_config_path()
    logger.info('Loading config from %s', config_path)
    config = GuardianConfig.from_file(config_path)
    ams = AMSClient(config)
    token = ams._ensure_token()
    
    # Get all miners
    try:
        miners = ams.get_miners()
        logger.info(f'Found {len(miners)} miners')
    except Exception as e:
        logger.error(f'Failed to get miners: {e}')
        return
    
    total_deleted = 0
    miners_cleaned = 0
    errors = 0
    
    for miner in miners:
        miner_id = miner.get('id')
        if not miner_id:
            continue
        
        try:
            logs = ams.get_log_list(miner_id)
        except Exception as e:
            logger.warning(f'Failed to get logs for miner {miner_id}: {e}')
            errors += 1
            continue
        
        if not logs:
            continue
        
        deleted = 0
        for log_entry in logs:
            log_id = log_entry.get('id')
            if not log_id:
                continue
            
            try:
                resp = ams.session.delete(
                    f'{ams.base_url}/log/delete',
                    json={'deviceID': miner_id, 'id': log_id},
                    headers={'Authorization': f'Bearer {token}'},
                    timeout=10
                )
                if resp.status_code == 200:
                    deleted += 1
                else:
                    errors += 1
            except Exception:
                errors += 1
            
            # Small delay to avoid hammering API
            time.sleep(0.05)
        
        if deleted > 0:
            logger.info(f'Miner {miner_id}: deleted {deleted} logs')
            total_deleted += deleted
            miners_cleaned += 1
    
    logger.info(f'CLEANUP COMPLETE: {total_deleted} logs deleted from {miners_cleaned} miners, {errors} errors')
    logger.info('=== AMS LOG CLEANUP END ===')


if __name__ == '__main__':
    cleanup_all_logs()
