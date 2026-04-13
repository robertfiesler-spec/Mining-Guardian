"""Auto-discovery integration — registers unknown fields in knowledge.unknown_fields.

When the parser encounters a field it doesn't recognize:
1. Check knowledge.field_registry — is this a known field?
2. If not, INSERT into knowledge.unknown_fields with provenance
3. Log it for review but NEVER skip the data
"""

import logging
from typing import Any, Optional

from config import TAG_DISCOVERY
from models import DetectedMiner

logger = logging.getLogger("importer.discovery")

# Known field keys that we expect — no need to register these
KNOWN_PARSER_FIELDS = {
    # Common miner fields
    "hashrate", "hashrate_th", "hashrate_5s", "hashrate_1m", "hashrate_15m",
    "hashrate_avg", "hashrate_ideal",
    "power", "power_w", "power_consumption",
    "efficiency", "efficiency_j_th",
    "temperature", "temp", "chip_temp", "board_temp", "pcb_temp",
    "inlet_temp", "outlet_temp", "ambient_temp",
    "fan_speed", "fan_rpm", "fan_pct",
    "voltage", "freq", "frequency",
    "psu_voltage", "psu_current", "psu_power", "psu_iout",
    "pool_url", "pool_user", "pool_password",
    "accepted", "rejected", "hw_errors", "stale",
    "uptime", "uptime_seconds", "elapsed",
    "serial", "serial_number", "sn",
    "mac", "mac_address",
    "ip", "ip_address",
    "firmware", "fw_version", "version",
    "model", "miner_type", "type",
    "chain", "chain_id", "board", "board_id",
    "chip_count", "chip_status", "asic_status",
    "dead_chips", "total_chips",
    "error_count", "warn_count", "fatal_count",
    "reboot_count", "restart_count",
    # Auradine-specific
    "dvfs", "power_state", "hitrate", "iout",
    "avg_volt", "target_freq", "actual_freq",
    # Bitmain-specific
    "chain_acn", "chain_rate", "chain_hw",
    "chain_temp_chip", "chain_temp_pcb",
    "bitmain_fan1", "bitmain_fan2", "bitmain_fan3", "bitmain_fan4",
    # MicroBT-specific
    "btminer_temp", "btminer_fan",
    "eeprom_hw_ver", "eeprom_fw_ver",
    # Generic
    "timestamp", "datetime", "date", "time",
    "error", "warning", "fatal", "critical", "info", "debug",
}


def _infer_type(value: Any) -> str:
    """Infer the raw_field_type from a Python value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return "string"


def _infer_category(field_name: str) -> Optional[str]:
    """Suggest a category based on field name heuristics."""
    name = field_name.lower()
    if any(kw in name for kw in ["temp", "thermal", "heat", "cool", "inlet", "outlet"]):
        return "thermal"
    if any(kw in name for kw in ["volt", "current", "power", "watt", "amp", "psu", "iout"]):
        return "electrical"
    if any(kw in name for kw in ["hash", "rate", "chip", "freq", "mhz", "ghz"]):
        return "performance"
    if any(kw in name for kw in ["fan", "humidity", "ambient", "pressure"]):
        return "environmental"
    if any(kw in name for kw in ["error", "fault", "warn", "fail", "restart", "reboot"]):
        return "safety"
    if any(kw in name for kw in ["serial", "mac", "ip", "hostname", "model"]):
        return "identity"
    if any(kw in name for kw in ["pool", "stratum", "accept", "reject", "stale"]):
        return "pool"
    if any(kw in name for kw in ["firmware", "version", "update", "flash"]):
        return "firmware"
    return None


class FieldDiscovery:
    """Discovers and registers unknown data fields encountered during parsing."""

    def __init__(self, db_conn=None):
        self._conn = db_conn
        self._registry_cache: Optional[set[str]] = None
        self._session_registered: set[str] = set()  # avoid duplicate inserts in one run

    def _load_registry(self) -> set[str]:
        """Load known field keys from field_registry into a set."""
        if self._registry_cache is not None:
            return self._registry_cache

        self._registry_cache = set(KNOWN_PARSER_FIELDS)

        if self._conn:
            try:
                from db import check_field_registry
                # We'll load all keys at once for efficiency
                import psycopg2.extras
                with self._conn.cursor() as cur:
                    cur.execute("SELECT field_key FROM knowledge.field_registry")
                    for row in cur.fetchall():
                        self._registry_cache.add(row[0])
            except Exception as e:
                logger.warning("Could not load field registry: %s", e)

        return self._registry_cache

    def check_and_register(
        self,
        field_name: str,
        value: Any,
        source_file: str,
        detected: Optional[DetectedMiner] = None,
        parent_object: Optional[str] = None,
    ) -> bool:
        """Check if a field is known. If not, register it as unknown.

        Returns True if the field was newly registered (unknown).
        """
        registry = self._load_registry()

        # Normalize the field name
        normalized = field_name.strip().lower().replace(" ", "_").replace("-", "_")

        # Check if known
        if normalized in registry:
            return False

        # Check if already registered this session
        dedup_key = f"{normalized}|{parent_object or ''}"
        if dedup_key in self._session_registered:
            return False

        self._session_registered.add(dedup_key)

        # Register as unknown
        raw_type = _infer_type(value)
        category = _infer_category(normalized)
        model_name = detected.display_name if detected else None

        logger.info(
            "%s New field discovered: %s = %s (type=%s, category=%s)",
            TAG_DISCOVERY,
            field_name,
            str(value)[:100],
            raw_type,
            category or "unknown",
        )

        if self._conn:
            try:
                from db import register_unknown_field
                register_unknown_field(
                    self._conn,
                    raw_field_name=field_name,
                    source_system="import",
                    source_endpoint=source_file,
                    raw_value=str(value)[:1000],
                    raw_type=raw_type,
                    source_model=model_name,
                    parent_object=parent_object,
                    suggested_category=category,
                )
            except Exception as e:
                logger.warning("Failed to register unknown field %s: %s", field_name, e)

        return True

    def process_raw_fields(
        self,
        raw_fields: dict[str, Any],
        source_file: str,
        detected: Optional[DetectedMiner] = None,
    ) -> list[dict[str, Any]]:
        """Process a dict of raw fields, registering any unknowns.

        Returns list of unknown field dicts for inclusion in ParsedData.
        """
        unknowns = []
        for key, value in raw_fields.items():
            if self.check_and_register(
                key, value, source_file, detected
            ):
                unknowns.append({
                    "field_name": key,
                    "raw_value": str(value)[:1000],
                    "inferred_type": _infer_type(value),
                    "suggested_category": _infer_category(key.lower()),
                })
        return unknowns
