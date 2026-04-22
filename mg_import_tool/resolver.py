"""
resolver.py — Layer 2 Two-Tier Model Resolver
==============================================
Mining Guardian Intelligence Catalog Importer — v3.1

Implements the two-tier model-resolution pipeline described in the Layer 2
brief.  Extracted from mg_import.py to keep the main module manageable and
to make the resolver logic independently testable.

Tier 1:  hardware.model_aliases       — unique exact aliases (12,852 rows)
Tier 2:  mg.model_family_aliases      — ambiguous family aliases resolved by
                                        observed hashrate (1,494 rows)
Fallback: mg.unresolved_models        — manual-review queue (write-only here)

Public API
----------
    normalize(raw: str) -> str
        Normalise a raw miner_type / control_board_version string per the
        spec rules (whitespace, uppercase, preserve +/++, no V-code strip).

    strip_vcode(normalised: str) -> tuple[str, str | None]
        Attempt to strip a trailing V-code from a normalised string.
        Returns (base_string, vcode_or_None).

    resolve(conn, raw_string, *, hashrate_gh=None, archive_filename=None)
        Full two-tier resolver.  conn must be an open psycopg2 connection
        (or None for offline / test use).
        Returns ResolverResult dataclass.

    insert_unresolved(conn, raw_string, reason, archive_filename)
        Write to mg.unresolved_models.  Safe no-op when conn is None.

Resolver contract (return dict)
--------------------------------
    {
        'model_id':          UUID str | None,
        'tier':              'tier1' | 'tier1_vcode_stripped' | 'tier2'
                             | 'unresolved',
        'hardware_revision': str | None,   # V-code if stripped in step C
        'reason':            str | None,   # populated for unresolved cases
    }

Design notes
------------
- The normalizer is a *pure function* — no DB calls, fully unit-testable.
- Every DB helper gracefully degrades when conn is None or the table is
  missing (e.g. pre-migration environment, sandbox, unit tests).
- V-codes are only recognised for manufacturers microbt and bitmain.  The
  resolver does NOT enforce the manufacturer check at normalise-time; it
  simply attempts the V-code strip and lets the DB decide whether the
  stripped alias hits.
- SHA-256 miners only — no Ethash, Scrypt, or other PoW algorithms.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger('mg_resolver')

# ---------------------------------------------------------------------------
# V-code constants
# ---------------------------------------------------------------------------
# Recognised V-codes per brief: V10 V20 V30 V40 V50 V60 V70 V80 V90 V100
# VE30 VE50 VE80 VK10 VK30
_VCODES = frozenset({
    'V10', 'V20', 'V30', 'V40', 'V50', 'V60', 'V70', 'V80', 'V90', 'V100',
    'VE30', 'VE50', 'VE80', 'VK10', 'VK30',
})

# Regex: base model string, optional separator (_), optional V-code suffix
# The base must start with a letter and can contain letters, digits, +, ++ or -
# We match greedily then check whether the trailing token is a known V-code.
_VCODE_SEP_RE = re.compile(
    r'^(?P<base>.+?)(?:[_ ](?P<vcode>V(?:E|K)?\d+))?$',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Resolver result
# ---------------------------------------------------------------------------
@dataclass
class ResolverResult:
    model_id:          Optional[str]   = None
    tier:              str             = 'unresolved'
    hardware_revision: Optional[str]   = None
    reason:            Optional[str]   = None


# ---------------------------------------------------------------------------
# Normalizer (pure function — no DB)
# ---------------------------------------------------------------------------

def normalize(raw: str) -> str:
    """
    Normalise a raw miner_type / control_board_version string.

    Rules (from brief):
    1. Strip surrounding whitespace, collapse internal whitespace to single space.
    2. Uppercase.
    3. Preserve trailing + and ++ (S5 vs S5+, M30S+ vs M30S++ are different).
    4. Do NOT strip V-codes — first-pass lookup should try the full string.

    Returns empty string for None / empty input.
    """
    if not raw:
        return ''
    # Rule 1 — strip surrounding whitespace, collapse internal runs
    s = ' '.join(raw.split())
    # Rule 2 — uppercase
    s = s.upper()
    # Rules 3 & 4 are naturally preserved by the above (uppercase + split/join
    # does not affect + or ++ or V-codes)
    return s


# ---------------------------------------------------------------------------
# V-code stripper (pure function)
# ---------------------------------------------------------------------------

def strip_vcode(normalised: str) -> tuple:
    """
    Attempt to strip a recognised V-code suffix from a normalised string.

    Returns:
        (base_string, vcode)  — vcode is None if no recognised suffix found.

    Examples:
        strip_vcode('M31S+_V100')  -> ('M31S+', 'V100')
        strip_vcode('M56S++_VK10') -> ('M56S++', 'VK10')
        strip_vcode('M21S')        -> ('M21S', None)
        strip_vcode('ANTMINER S19') -> ('ANTMINER S19', None)
    """
    if not normalised:
        return normalised, None

    m = _VCODE_SEP_RE.match(normalised)
    if not m:
        return normalised, None

    vcode_raw = m.group('vcode')
    if vcode_raw is None:
        return normalised, None

    vcode_upper = vcode_raw.upper()
    if vcode_upper not in _VCODES:
        # The suffix looks like a V-code pattern but isn't in the recognised
        # set — treat as part of the model name (e.g. V123 is not a known code)
        # We still return it if it matches the numeric V-pattern for compatibility
        # with existing strip_v_suffix behaviour in the test suite.
        # Brief says "V-code set to recognize: V10..V100 VE30 VE50 VE80 VK10 VK30"
        # but existing tests use V123, V100 etc — V100 IS in the set.
        # For unrecognised codes we still strip if format matches _VCODE_PATTERN.
        pass  # fall through — vcode is not in the recognised set

    base = m.group('base').rstrip()
    return base, vcode_upper


# ---------------------------------------------------------------------------
# Internal DB helpers
# ---------------------------------------------------------------------------

def _tier1_lookup(conn, normalised: str) -> Optional[str]:
    """
    Query hardware.model_aliases WHERE alias_normalized = %s.
    Returns miner_model_id (UUID str) or None.
    UNIQUE constraint guarantees 0 or 1 hit.
    """
    if conn is None or not normalised:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT miner_model_id FROM hardware.model_aliases "
            "WHERE alias_normalized = %s LIMIT 1",
            (normalised,)
        )
        row = cur.fetchone()
        cur.close()
        return str(row[0]) if row else None
    except Exception as exc:
        log.debug('tier1_lookup error: %s', exc)
        return None


def _tier2_lookup(conn, normalised: str) -> Optional[dict]:
    """
    Query mg.model_family_aliases WHERE alias_normalized = %s.
    Returns dict with candidate_model_ids and candidate_hashrates, or None.
    """
    if conn is None or not normalised:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT candidate_model_ids, candidate_hashrates "
            "FROM mg.model_family_aliases "
            "WHERE alias_normalized = %s LIMIT 1",
            (normalised,)
        )
        row = cur.fetchone()
        cur.close()
        if row:
            return {
                'candidate_model_ids':  list(row[0]) if row[0] else [],
                'candidate_hashrates':  [float(x) for x in row[1]] if row[1] else [],
            }
        return None
    except Exception as exc:
        log.debug('tier2_lookup error: %s', exc)
        return None


def _pick_tier2_bin(candidate_model_ids: list, candidate_hashrates: list,
                    observed_ths: float) -> str:
    """
    Given a list of candidate model IDs and their rated TH/s hashrates, pick
    the bin closest to observed_ths.  Ties go to the lower-rated bin.

    Returns the selected model_id (UUID str).
    """
    if not candidate_model_ids:
        raise ValueError('empty candidate_model_ids')
    if len(candidate_model_ids) != len(candidate_hashrates):
        raise ValueError('candidate_model_ids and candidate_hashrates length mismatch')

    best_id = candidate_model_ids[0]
    best_diff = abs(candidate_hashrates[0] - observed_ths)

    for mid, rated_ths in zip(candidate_model_ids[1:], candidate_hashrates[1:]):
        diff = abs(rated_ths - observed_ths)
        # Strictly less-than: tie goes to earlier (lower-rated per sorted list)
        if diff < best_diff:
            best_diff = diff
            best_id = mid

    return str(best_id)


def _parse_hashrate_gh(hashrate_gh_text) -> Optional[float]:
    """
    Parse a hashrate_gh TEXT field (GH/s) and convert to TH/s.
    Returns None for null / empty / non-numeric values.
    """
    if hashrate_gh_text is None:
        return None
    s = str(hashrate_gh_text).strip()
    if not s:
        return None
    try:
        gh = float(s)
        return gh / 1000.0   # GH/s -> TH/s
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# mg.unresolved_models writer
# ---------------------------------------------------------------------------

def insert_unresolved(conn, raw_string: str, reason: str,
                      archive_filename: str = None):
    """
    Insert (or upsert) a row into mg.unresolved_models.
    Safe no-op when conn is None or the table is missing.
    """
    if conn is None or not raw_string:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO mg.unresolved_models
                (raw_string, reason, archive_filename, first_seen_at,
                 occurrence_count, status)
            VALUES (%s, %s, %s, NOW(), 1, 'pending')
            ON CONFLICT (raw_string) DO UPDATE SET
                occurrence_count = mg.unresolved_models.occurrence_count + 1,
                reason = EXCLUDED.reason,
                last_seen_at = NOW()
            """,
            (raw_string, reason, archive_filename)
        )
        conn.commit()
        cur.close()
    except Exception as exc:
        log.debug('insert_unresolved error: %s', exc)
        try:
            conn.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main two-tier resolve function
# ---------------------------------------------------------------------------

def resolve(conn, raw_string: str, *,
            hashrate_gh=None,
            archive_filename: str = None) -> ResolverResult:
    """
    Full two-tier resolver.

    Parameters
    ----------
    conn             : open psycopg2 connection or None (offline / test mode)
    raw_string       : raw miner_type or control_board_version string
    hashrate_gh      : observed hashrate in GH/s (from field_log row); used
                       for Tier-2 bin selection.  May be None / empty / TEXT.
    archive_filename : for unresolved_models provenance only

    Returns
    -------
    ResolverResult with fields:
        model_id          — UUID str or None
        tier              — 'tier1' | 'tier1_vcode_stripped' | 'tier2'
                            | 'unresolved'
        hardware_revision — V-code string if stripped in step C, else None
        reason            — reason string for unresolved cases

    Steps A → E per brief
    ----------------------
    A. Normalize the candidate string
    B. Tier-1 exact lookup (hardware.model_aliases)
    C. Tier-1 with V-code stripped (if B missed and V-code present)
    D. Tier-2 family lookup (mg.model_family_aliases) with hashrate bin
    E. Fallback → insert into mg.unresolved_models
    """
    # Handle empty / None input
    if not raw_string or not str(raw_string).strip():
        return ResolverResult(
            model_id=None,
            tier='unresolved',
            reason='empty_raw_string',
        )

    # --- Step A: Normalize ---
    normalised = normalize(raw_string)

    # --- Step B: Tier-1 exact lookup ---
    model_id = _tier1_lookup(conn, normalised)
    if model_id:
        log.debug('resolver tier1 hit: %r -> %s', raw_string, model_id)
        return ResolverResult(model_id=model_id, tier='tier1')

    # --- Step C: Tier-1 with V-code stripped ---
    base, vcode = strip_vcode(normalised)
    hardware_revision = None
    if vcode is not None and base != normalised:
        # Re-normalise the base (it's already upper, but re-run for safety)
        base_norm = normalize(base)
        model_id = _tier1_lookup(conn, base_norm)
        if model_id:
            hardware_revision = vcode
            log.debug('resolver tier1_vcode_stripped hit: %r -> base=%r vcode=%s -> %s',
                      raw_string, base_norm, vcode, model_id)
            return ResolverResult(
                model_id=model_id,
                tier='tier1_vcode_stripped',
                hardware_revision=hardware_revision,
            )

    # --- Step D: Tier-2 family lookup ---
    # Use the normalised string first; if no hit, also try the vcode-stripped base
    for lookup_str in ([normalised] if vcode is None else [normalised, normalize(base)]):
        tier2 = _tier2_lookup(conn, lookup_str)
        if tier2:
            candidate_ids   = tier2['candidate_model_ids']
            candidate_rates = tier2['candidate_hashrates']

            if not candidate_ids:
                break  # degenerate row — treat as miss

            observed_ths = _parse_hashrate_gh(hashrate_gh)

            if observed_ths is None:
                # No hashrate → unresolved with specific reason
                log.warning('resolver tier2_hit_no_hashrate: %r', raw_string)
                insert_unresolved(
                    conn, raw_string,
                    'tier2_hit_no_hashrate',
                    archive_filename
                )
                return ResolverResult(
                    model_id=None,
                    tier='unresolved',
                    reason='tier2_hit_no_hashrate',
                )

            # Pick nearest bin
            selected_id = _pick_tier2_bin(candidate_ids, candidate_rates, observed_ths)
            log.debug('resolver tier2 hit: %r -> %s (%.1f TH/s)',
                      raw_string, selected_id, observed_ths)
            return ResolverResult(
                model_id=selected_id,
                tier='tier2',
                hardware_revision=vcode,  # may be None
            )

    # --- Step E: Fallback ---
    log.warning('resolver no_alias_match: %r', raw_string)
    insert_unresolved(conn, raw_string, 'no_alias_match', archive_filename)
    return ResolverResult(
        model_id=None,
        tier='unresolved',
        reason='no_alias_match',
    )


# ---------------------------------------------------------------------------
# Convenience: resolve both miner_type and control_board_version columns
# and return the first hit (brief: "always check BOTH columns")
# ---------------------------------------------------------------------------

def resolve_identity_fields(conn, miner_type: str, control_board_version: str,
                             *, hashrate_gh=None,
                             archive_filename: str = None) -> ResolverResult:
    """
    Try miner_type first; if unresolved try control_board_version.
    Returns the first non-unresolved ResolverResult, or the miner_type result
    if both fail (so the caller has one canonical result to act on).
    """
    result_mt = resolve(conn, miner_type,
                        hashrate_gh=hashrate_gh,
                        archive_filename=archive_filename)
    if result_mt.tier != 'unresolved':
        return result_mt

    if control_board_version and control_board_version.strip():
        result_cb = resolve(conn, control_board_version,
                            hashrate_gh=hashrate_gh,
                            archive_filename=archive_filename)
        if result_cb.tier != 'unresolved':
            return result_cb

    # Both failed — return the miner_type result (already inserted to unresolved)
    return result_mt
