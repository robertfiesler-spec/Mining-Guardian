"""
S19J Pro Overheating Handler
Operator Rule #6: Try ONE restart for overheating S19J Pros.
If it doesn't help, mark as aging hardware and let them run.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def check_s19jpro_overheat_status(db_path: str, miner_id: str, model: str, ip: str) -> Tuple[str, Optional[str]]:
    """
    Check if this S19J Pro has already had its overheating restart attempt.
    
    Returns:
        (status, notes)
        - ('new', None) — First time seeing overheat, should try restart
        - ('restart_pending', None) — Restart was done, waiting for comparison
        - ('aging', notes) — Already tried, didn't help, let it run
    """
    if not model or not model.startswith('S19JPro'):
        return ('not_s19jpro', None)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    row = conn.execute(
        'SELECT * FROM s19jpro_overheat_tracking WHERE miner_id = ?',
        (miner_id,)
    ).fetchone()
    
    conn.close()
    
    if not row:
        return ('new', None)
    
    if row['marked_aging_at']:
        return ('aging', row['notes'])
    
    if row['restart_attempted_at'] and row['restart_helped'] is None:
        return ('restart_pending', None)
    
    if row['restart_helped'] == 0:
        return ('aging', row['notes'])
    
    return ('new', None)


def record_overheat_first_seen(db_path: str, miner_id: str, ip: str):
    """Record first time we see this S19J Pro overheating."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('''
            INSERT OR IGNORE INTO s19jpro_overheat_tracking (miner_id, ip, first_overheat_at)
            VALUES (?, ?, ?)
        ''', (miner_id, ip, datetime.now().isoformat()))
        conn.commit()
        logger.info(f'Recorded first overheat for S19J Pro {miner_id} ({ip})')
    finally:
        conn.close()


def record_restart_attempt(db_path: str, miner_id: str, log_before: str = None):
    """Record that we attempted a restart for overheating."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('''
            UPDATE s19jpro_overheat_tracking
            SET restart_attempted_at = ?, log_before = ?
            WHERE miner_id = ?
        ''', (datetime.now().isoformat(), log_before, miner_id))
        conn.commit()
        logger.info(f'Recorded restart attempt for S19J Pro {miner_id}')
    finally:
        conn.close()


def record_restart_result(db_path: str, miner_id: str, helped: bool, log_after: str = None, notes: str = None):
    """Record whether the restart helped."""
    conn = sqlite3.connect(db_path)
    try:
        if helped:
            # Restart worked - remove from tracking
            conn.execute('DELETE FROM s19jpro_overheat_tracking WHERE miner_id = ?', (miner_id,))
            logger.info(f'Restart helped S19J Pro {miner_id} - removed from tracking')
        else:
            # Restart didn't help - mark as aging
            conn.execute('''
                UPDATE s19jpro_overheat_tracking
                SET restart_helped = 0, log_after = ?, marked_aging_at = ?, 
                    notes = ?
                WHERE miner_id = ?
            ''', (log_after, datetime.now().isoformat(), 
                  notes or 'Aging hardware - restart did not resolve overheating', miner_id))
            logger.info(f'Marked S19J Pro {miner_id} as aging hardware')
        conn.commit()
    finally:
        conn.close()


def get_aging_s19jpros(db_path: str) -> list:
    """Get list of S19J Pros marked as aging (for suppression in reports)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT miner_id, ip, notes FROM s19jpro_overheat_tracking WHERE marked_aging_at IS NOT NULL'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == '__main__':
    # Test
    print('S19J Pro Overheat Handler loaded')
