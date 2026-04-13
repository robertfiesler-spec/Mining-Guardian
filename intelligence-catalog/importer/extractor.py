"""Universal file extractor — handles archives, PDFs, logs, CSVs, and text files.

Extracts contents from zip/tar/7z/gzip archives into a temp directory,
reads PDFs to text, and handles plain text with encoding detection.
"""

import gzip
import hashlib
import logging
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Generator, Optional

import chardet

from config import (
    ALL_SUPPORTED_EXTS,
    MAX_FILE_SIZE_MB,
    SUPPORTED_ARCHIVE_EXTS,
    SUPPORTED_DOC_EXTS,
    SUPPORTED_TEXT_EXTS,
)
from models import ExtractedFile

logger = logging.getLogger("importer.extractor")


def sha256_hash(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_encoding(filepath: str) -> str:
    """Detect text file encoding using chardet."""
    with open(filepath, "rb") as f:
        raw = f.read(65536)
    result = chardet.detect(raw)
    return result.get("encoding") or "utf-8"


def read_text_file(filepath: str) -> str:
    """Read a text file with encoding detection."""
    encoding = detect_encoding(filepath)
    try:
        with open(filepath, "r", encoding=encoding, errors="replace") as f:
            return f.read()
    except Exception as e:
        logger.warning("Failed to read %s with encoding %s: %s", filepath, encoding, e)
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


def read_pdf(filepath: str) -> str:
    """Extract text from a PDF file."""
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(filepath)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)
    except Exception as e:
        logger.warning("PDF extraction failed for %s: %s", filepath, e)
        return ""


def classify_file_type(ext: str) -> str:
    """Classify a file extension into a category."""
    ext = ext.lower()
    if ext in {".log"}:
        return "log"
    if ext in {".csv", ".tsv"}:
        return "csv"
    if ext in {".pdf"}:
        return "pdf"
    if ext in SUPPORTED_ARCHIVE_EXTS:
        return "archive"
    if ext in {".txt", ".json", ".xml", ".conf", ".cfg"}:
        return "text"
    return "unknown"


def _extract_zip(archive_path: str, dest_dir: str) -> list[str]:
    """Extract a zip archive and return list of extracted file paths."""
    extracted = []
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # Skip macOS resource forks and hidden files
            if info.filename.startswith("__MACOSX") or "/." in info.filename:
                continue
            try:
                out_path = zf.extract(info, dest_dir)
                extracted.append(out_path)
            except RuntimeError as e:
                if "encrypted" in str(e).lower() or "password" in str(e).lower():
                    logger.warning("Skipping encrypted file in zip: %s — %s", info.filename, e)
                else:
                    logger.error("Failed to extract %s: %s", info.filename, e)
            except Exception as e:
                logger.error("Failed to extract %s: %s", info.filename, e)
    return extracted


def _extract_tar(archive_path: str, dest_dir: str) -> list[str]:
    """Extract a tar/tar.gz/tar.bz2 archive."""
    extracted = []
    with tarfile.open(archive_path, "r:*") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            if member.name.startswith("__MACOSX") or "/." in member.name:
                continue
            tf.extract(member, dest_dir, filter="data")
            extracted.append(os.path.join(dest_dir, member.name))
    return extracted


def _extract_7z(archive_path: str, dest_dir: str) -> list[str]:
    """Extract a 7z archive."""
    try:
        import py7zr

        extracted = []
        with py7zr.SevenZipFile(archive_path, mode="r") as z:
            z.extractall(path=dest_dir)
        # Walk extracted directory to find all files
        for root, _dirs, files in os.walk(dest_dir):
            for f in files:
                extracted.append(os.path.join(root, f))
        return extracted
    except ImportError:
        logger.error("py7zr not installed — cannot extract .7z files")
        return []
    except Exception as e:
        logger.error("7z extraction failed for %s: %s", archive_path, e)
        return []


def _extract_gzip(archive_path: str, dest_dir: str) -> list[str]:
    """Extract a standalone .gz file (not tar.gz)."""
    out_name = Path(archive_path).stem  # removes .gz
    out_path = os.path.join(dest_dir, out_name)
    try:
        with gzip.open(archive_path, "rb") as gz_in:
            with open(out_path, "wb") as f_out:
                shutil.copyfileobj(gz_in, f_out)
        return [out_path]
    except Exception as e:
        logger.error("Gzip extraction failed for %s: %s", archive_path, e)
        return []


def _is_archive(filepath: str) -> bool:
    """Check if a filepath looks like a supported archive, handling special characters in names."""
    ext = "".join(Path(filepath).suffixes).lower()
    if ext in SUPPORTED_ARCHIVE_EXTS:
        return True
    # Fallback: check the lowered filename directly for known archive endings
    filename_lower = filepath.lower()
    return any(
        filename_lower.endswith(suffix)
        for suffix in (".tar.gz", ".tgz", ".tar.bz2", ".tar", ".zip", ".7z", ".gz")
    )


def extract_archive(archive_path: str, dest_dir: str) -> list[str]:
    """Extract any supported archive format and return list of extracted file paths."""
    ext = "".join(Path(archive_path).suffixes).lower()
    filename_lower = archive_path.lower()

    # Try Path-based extension first, then fall back to string endswith for
    # filenames with special characters (e.g. parentheses) that confuse Path.suffixes
    if ext in {".zip"} or filename_lower.endswith(".zip"):
        return _extract_zip(archive_path, dest_dir)
    elif ext in {".tar", ".tar.gz", ".tgz", ".tar.bz2"} or filename_lower.endswith(
        (".tar.gz", ".tgz", ".tar.bz2", ".tar")
    ):
        return _extract_tar(archive_path, dest_dir)
    elif ext in {".7z"} or filename_lower.endswith(".7z"):
        return _extract_7z(archive_path, dest_dir)
    elif (ext in {".gz"} and ".tar" not in ext) or (
        filename_lower.endswith(".gz") and not filename_lower.endswith(".tar.gz")
    ):
        return _extract_gzip(archive_path, dest_dir)
    else:
        logger.warning("Unsupported archive format: %s", ext)
        return []


def extract_files(
    path: str, temp_dir: Optional[str] = None
) -> Generator[ExtractedFile, None, None]:
    """Extract/enumerate all processable files from a path.

    If path is a file: yield that single file (extracting if archive).
    If path is a directory: recursively yield all files.
    """
    path = os.path.abspath(path)
    own_temp = False
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp(prefix="ic_import_")
        own_temp = True

    try:
        if os.path.isfile(path):
            yield from _process_single_file(path, temp_dir)
        elif os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for fname in sorted(files):
                    fpath = os.path.join(root, fname)
                    yield from _process_single_file(fpath, temp_dir)
        else:
            logger.error("Path does not exist: %s", path)
    finally:
        if own_temp and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def _process_single_file(
    filepath: str, temp_dir: str
) -> Generator[ExtractedFile, None, None]:
    """Process a single file — extract if archive, otherwise yield directly."""
    filepath = os.path.abspath(filepath)
    ext = Path(filepath).suffix.lower()
    combined_ext = "".join(Path(filepath).suffixes).lower()
    file_size = os.path.getsize(filepath)

    # Check size limit
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        logger.warning("Skipping %s — exceeds %dMB size limit", filepath, MAX_FILE_SIZE_MB)
        return

    # Handle archives — extract and recurse
    if ext in SUPPORTED_ARCHIVE_EXTS or combined_ext in SUPPORTED_ARCHIVE_EXTS or _is_archive(filepath):
        archive_dest = os.path.join(temp_dir, Path(filepath).stem)
        os.makedirs(archive_dest, exist_ok=True)
        extracted_paths = extract_archive(filepath, archive_dest)
        logger.info("Extracted %d files from %s", len(extracted_paths), filepath)

        for epath in extracted_paths:
            yield from _process_single_file(epath, temp_dir)
        return

    # Handle text files
    if ext in SUPPORTED_TEXT_EXTS or ext == "":
        content = read_text_file(filepath)
        yield ExtractedFile(
            original_path=filepath,
            working_path=filepath,
            filename=os.path.basename(filepath),
            extension=ext,
            file_size=file_size,
            file_hash=sha256_hash(filepath),
            file_type=classify_file_type(ext),
            content=content,
        )
        return

    # Handle PDFs
    if ext in SUPPORTED_DOC_EXTS:
        content = read_pdf(filepath)
        yield ExtractedFile(
            original_path=filepath,
            working_path=filepath,
            filename=os.path.basename(filepath),
            extension=ext,
            file_size=file_size,
            file_hash=sha256_hash(filepath),
            file_type="pdf",
            content=content,
        )
        return

    # Unknown extension — try to read as text anyway (never skip)
    logger.info("Unknown extension %s — attempting text read for %s", ext, filepath)
    try:
        content = read_text_file(filepath)
        yield ExtractedFile(
            original_path=filepath,
            working_path=filepath,
            filename=os.path.basename(filepath),
            extension=ext,
            file_size=file_size,
            file_hash=sha256_hash(filepath),
            file_type="unknown",
            content=content,
        )
    except Exception as e:
        logger.warning("Could not read %s: %s", filepath, e)
        yield ExtractedFile(
            original_path=filepath,
            working_path=filepath,
            filename=os.path.basename(filepath),
            extension=ext,
            file_size=file_size,
            file_hash=sha256_hash(filepath),
            file_type="unknown",
            content="",
        )
