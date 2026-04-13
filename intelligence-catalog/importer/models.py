"""Data models for the Intelligence Catalog Importer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class DetectedMiner:
    """Result of the miner detection engine."""
    brand: Optional[str] = None
    model: Optional[str] = None
    firmware: Optional[str] = None
    serial: Optional[str] = None
    mac: Optional[str] = None
    ip_address: Optional[str] = None
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    catalog_model_id: Optional[str] = None  # UUID from hardware.miner_models
    catalog_name: Optional[str] = None
    manufacturer_id: Optional[str] = None
    algorithm: str = "SHA-256"
    stock_hashrate_th: Optional[float] = None
    stock_power_w: Optional[float] = None

    @property
    def needs_review(self) -> bool:
        return self.confidence < 0.80

    @property
    def display_name(self) -> str:
        parts = []
        if self.brand:
            parts.append(self.brand.title())
        if self.model:
            parts.append(self.model)
        if self.firmware:
            parts.append(f"(fw: {self.firmware})")
        return " ".join(parts) if parts else "Unknown"


@dataclass
class ParsedData:
    """Output from any parser — a bag of structured data extracted from a file."""
    # Summary metrics
    hashrate_th: Optional[float] = None
    power_w: Optional[float] = None
    efficiency_j_th: Optional[float] = None
    uptime_seconds: Optional[int] = None

    # Per-chain / per-board data
    chains: list[dict[str, Any]] = field(default_factory=list)
    boards: list[dict[str, Any]] = field(default_factory=list)

    # Temperature readings
    chip_temps: list[float] = field(default_factory=list)
    board_temps: list[float] = field(default_factory=list)
    inlet_temp: Optional[float] = None
    outlet_temp: Optional[float] = None

    # Fan data
    fan_speeds: list[int] = field(default_factory=list)

    # Electrical
    voltages: list[float] = field(default_factory=list)
    frequencies: list[float] = field(default_factory=list)
    psu_voltage: Optional[float] = None
    psu_current: Optional[float] = None

    # Pool data
    pool_url: Optional[str] = None
    pool_user: Optional[str] = None
    accepted_shares: Optional[int] = None
    rejected_shares: Optional[int] = None
    hw_errors: Optional[int] = None

    # Error / event counters
    error_count: int = 0
    warn_count: int = 0
    fatal_count: int = 0
    reboot_count: int = 0

    # Dead chips
    dead_chips: int = 0
    total_chips: Optional[int] = None

    # Raw extracted key-value pairs (everything we found)
    raw_fields: dict[str, Any] = field(default_factory=dict)

    # Unknown fields discovered during parsing
    unknown_fields: list[dict[str, Any]] = field(default_factory=list)

    # Timestamps
    log_start: Optional[datetime] = None
    log_end: Optional[datetime] = None

    # Parser metadata
    parser_name: str = ""
    data_points_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for database storage."""
        result = {}
        for k, v in self.__dict__.items():
            if v is None:
                continue
            if isinstance(v, datetime):
                result[k] = v.isoformat()
            elif isinstance(v, list) and v:
                result[k] = v
            elif isinstance(v, dict) and v:
                result[k] = v
            elif isinstance(v, (int, float, str, bool)) and v:
                result[k] = v
        return result


@dataclass
class TestResult:
    """Result of a single diagnostic test."""
    test_id: str
    test_name: str
    category: str  # 'universal', 'brand_specific', 'model_specific'
    result: str  # 'PASS', 'WARN', 'FAIL', 'SKIP', 'ERROR'
    severity: str = "LOW"  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    evidence: str = ""
    diagnosis: str = ""
    recommended_action: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedFile:
    """A file that has been extracted/identified for processing."""
    original_path: str
    working_path: str  # may differ if extracted from archive
    filename: str
    extension: str
    file_size: int
    file_hash: str  # SHA-256
    file_type: str  # 'log', 'csv', 'pdf', 'text', 'archive', 'unknown'
    content: Optional[str] = None  # text content if applicable
    binary_content: Optional[bytes] = None
    is_from_archive: bool = False
    archive_path: Optional[str] = None


@dataclass
class ImportJob:
    """Tracks an entire import operation."""
    import_id: Optional[int] = None
    started_at: Optional[datetime] = None
    source_path: str = ""
    source_type: str = "file"
    total_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    needs_review: int = 0
    status: str = "running"
    notes: str = ""
