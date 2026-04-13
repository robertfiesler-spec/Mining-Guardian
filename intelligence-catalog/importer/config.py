"""Configuration constants for the Intelligence Catalog Importer."""

import os

# ─── Database connection (PostgreSQL 16 on ROBS-PC) ──────────────────────────
DB_HOST = os.environ.get("IC_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("IC_DB_PORT", "5432"))
DB_NAME = os.environ.get("IC_DB_NAME", "mining_guardian")
DB_USER = os.environ.get("IC_DB_USER", "guardian_admin")
DB_PASSWORD = os.environ.get("IC_DB_PASSWORD", "")
DB_CONTAINER = "mining-guardian-db"

# ─── Detection thresholds ─────────────────────────────────────────────────────
DETECTION_CONFIDENCE_THRESHOLD = 0.80  # below this → needs_review
HEADER_SCAN_BYTES = 4096               # read first 4KB for header detection

# ─── Operational thresholds (Bobby's rules) ───────────────────────────────────
MAX_CHIP_TEMP_C = 84.0   # operator rule: 84°C threshold
MIN_HITRATE = 0.90        # Auradine: hitrate below 0.90 is a problem
POOL_REJECT_WARN_PCT = 2.0
POOL_REJECT_FAIL_PCT = 5.0

# ─── File handling ────────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB = 500
SUPPORTED_ARCHIVE_EXTS = {".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".7z", ".gz"}
SUPPORTED_TEXT_EXTS = {".log", ".txt", ".csv", ".tsv", ".json", ".xml", ".conf", ".cfg"}
SUPPORTED_DOC_EXTS = {".pdf"}
ALL_SUPPORTED_EXTS = SUPPORTED_ARCHIVE_EXTS | SUPPORTED_TEXT_EXTS | SUPPORTED_DOC_EXTS

# ─── Algorithm filter ─────────────────────────────────────────────────────────
BITCOIN_SHA256_ONLY = True

# Non-SHA-256 algorithm keywords — if detected, skip the file
NON_SHA256_ALGORITHMS = {
    "ethash", "etchash", "scrypt", "x11", "equihash", "randomx", "cryptonight",
    "kawpow", "octopus", "autolykos", "blake2b", "blake2s", "eaglesong",
    "handshake", "kadena", "nervos", "sia", "decred", "zcash", "litecoin",
    "ethereum", "kaspa", "kheavyhash", "blake3",
}

# Brands known to be Bitcoin SHA-256
SHA256_BRANDS = {"bitmain", "microbt", "canaan", "auradine", "bitdeer", "strongu"}

# ─── ANSI color codes for terminal output ─────────────────────────────────────
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    @staticmethod
    def tag(label: str, color: str) -> str:
        return f"{color}[{label}]{Color.RESET}"

# Shorthand tags for CLI output
TAG_IMPORT = Color.tag("IMPORT", Color.CYAN)
TAG_EXTRACT = Color.tag("EXTRACT", Color.BLUE)
TAG_DETECT = Color.tag("DETECT", Color.MAGENTA)
TAG_PARSE = Color.tag("PARSE", Color.GREEN)
TAG_TEST = Color.tag("TEST", Color.YELLOW)
TAG_STORE = Color.tag("STORE", Color.GREEN)
TAG_SKIP = Color.tag("SKIP", Color.DIM)
TAG_WARN = Color.tag("WARN", Color.YELLOW)
TAG_ERROR = Color.tag("ERROR", Color.RED)
TAG_DISCOVERY = Color.tag("DISCOVERY", Color.MAGENTA)
TAG_OK = Color.tag("OK", Color.GREEN)
