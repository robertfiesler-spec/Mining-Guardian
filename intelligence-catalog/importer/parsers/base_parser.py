"""Abstract base class for all miner log/data parsers."""

from abc import ABC, abstractmethod

from models import DetectedMiner, ParsedData


class BaseParser(ABC):
    """Base class that all brand-specific parsers must extend."""

    # Human-readable name for this parser
    name: str = "base"

    @abstractmethod
    def can_parse(self, content: str, detected: DetectedMiner) -> bool:
        """Return True if this parser can handle the given content.

        Args:
            content: The text content of the file.
            detected: The miner detection result.
        """
        ...

    @abstractmethod
    def parse(self, content: str, detected: DetectedMiner) -> ParsedData:
        """Parse the content and return structured data.

        Args:
            content: The text content of the file.
            detected: The miner detection result with brand/model info.

        Returns:
            ParsedData with all extracted fields populated.
        """
        ...

    def _count_data_points(self, data: ParsedData) -> int:
        """Count total data points extracted."""
        count = 0
        for k, v in data.__dict__.items():
            if k.startswith("_") or k in ("parser_name", "data_points_count", "unknown_fields"):
                continue
            if isinstance(v, list):
                count += len(v)
            elif isinstance(v, dict):
                count += len(v)
            elif v is not None and v != 0 and v != "":
                count += 1
        return count
