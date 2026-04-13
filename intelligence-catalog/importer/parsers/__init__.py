"""Brand-specific and generic parsers for miner log/data files."""

from .base_parser import BaseParser
from .bitmain_parser import BitmainParser
from .microbt_parser import MicroBTParser
from .auradine_parser import AuradineParser
from .canaan_parser import CanaanParser
from .csv_parser import CSVParser
from .generic_parser import GenericParser

ALL_PARSERS = [
    BitmainParser,
    MicroBTParser,
    AuradineParser,
    CanaanParser,
    CSVParser,
    GenericParser,  # fallback — must be last
]

__all__ = [
    "BaseParser",
    "BitmainParser",
    "MicroBTParser",
    "AuradineParser",
    "CanaanParser",
    "CSVParser",
    "GenericParser",
    "ALL_PARSERS",
]
