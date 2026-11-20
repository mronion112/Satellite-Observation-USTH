"""Retrying, binary-safe downloads for satellite reception files."""

from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests

from config import (
    DOWNLOAD_CHUNK_SIZE,
    MAX_DOWNLOAD_WORKERS,
    MAX_RETRIES,
    OVERWRITE,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_SECONDS,
)
from scraper import DATA_TYPE_FILENAMES, Reception, build_reception_directory

DownloadStatus = Literal["downloaded", "skipped", "failed"]
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass
class DownloadResult:
    """Outcome of one file download."""

    status: DownloadStatus
    destination: Path
    bytes_downloaded: int = 0
    error: str | None = None


def _remove_temp_file(path: str | None) -> None:
    if path:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def download_file(
    url: str,
    destination: str | Path,
    overwrite: bool = OVERWRITE,
) -> DownloadResult:
    """Stream a URL to disk, retry temporary failures, and avoid partial files.

    Downloads first go to a temporary file in the destination directory. A
    completed file is then committed atomically, without replacing an existing
    destination unless ``overwrite`` is true.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and not overwrite:
        if destination.is_file():
            return DownloadResult("skipped", destination, error="file already exists")
        return DownloadResult("failed", destination, error="destination exists and is not a file")

    total_attempts = max(1, MAX_RETRIES + 1)
    retryable_exceptions = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
        requests.exceptions.ContentDecodingError,
    )

    for attempt in range(1, total_attempts + 1):
        temporary_path: str | None = None
        try:
            with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT) as response:
                if response.status_code >= 400:
                    error = f"HTTP {response.status_code} for {url}"
                    if response.status_code in RETRYABLE_STATUS_CODES and attempt < total_attempts:
                        time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                        continue
                    return DownloadResult("failed", destination, error=error)

                file_descriptor, temporary_path = tempfile.mkstemp(
                    prefix=f".{destination.name}.",
                    suffix=".part",
                    dir=destination.parent,
                )
                bytes_written = 0
                with os.fdopen(file_descriptor, "wb") as output_file:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            output_file.write(chunk)
                            bytes_written += len(chunk)

            if overwrite:
                os.replace(temporary_path, destination)
            else:
                try:
                    # A hard link gives us an atomic, no-clobber commit.
                    os.link(temporary_path, destination)
                except FileExistsError:
                    _remove_temp_file(temporary_path)
                    temporary_path = None
                    return DownloadResult(
                        "skipped", destination, error="file already exists"
                    )
                os.unlink(temporary_path)
            temporary_path = None
            return DownloadResult("downloaded", destination, bytes_downloaded=bytes_written)

        except retryable_exceptions as exc:
            _remove_temp_file(temporary_path)
            if attempt < total_attempts:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            return DownloadResult("failed", destination, error=str(exc))
        except KeyboardInterrupt:
            _remove_temp_file(temporary_path)
            raise
        except (requests.exceptions.RequestException, OSError) as exc:
            _remove_temp_file(temporary_path)
            return DownloadResult("failed", destination, error=str(exc))

    return DownloadResult("failed", destination, error="download failed after retries")


def download_reception_files(
    reception: Reception,
    output_dir: str | Path,
    overwrite: bool = OVERWRITE,
) -> dict[str, DownloadResult]:
    """Download the available files for one reception using worker threads."""
    completed = download_receptions_files([reception], output_dir, overwrite)
    return {file_type: result for _, file_type, result in completed}


def download_receptions_files(
    receptions: list[Reception],
    output_dir: str | Path,
    overwrite: bool = OVERWRITE,
    max_workers: int = MAX_DOWNLOAD_WORKERS,
) -> list[tuple[Reception, str, DownloadResult]]:
    """Download files across all receptions with a shared bounded worker pool.

    Results are returned in completion order so the caller can report progress
    as each independent download finishes.
    """
    jobs: list[tuple[Reception, str, str, Path]] = []
    for reception in receptions:
        if reception.timestamp is None:
            continue
        reception_dir = build_reception_directory(reception.timestamp, output_dir)
        for file_type, filename in DATA_TYPE_FILENAMES.items():
            url = reception.links.get(file_type)
            if url:
                jobs.append((reception, file_type, url, reception_dir / filename))

    if not jobs:
        return []

    results: list[tuple[Reception, str, DownloadResult]] = []
    worker_count = max(1, max_workers)
    executor = ThreadPoolExecutor(
        max_workers=worker_count, thread_name_prefix="satellite-download"
    )
    future_to_job = {}
    try:
        for reception, file_type, url, destination in jobs:
            future = executor.submit(download_file, url, destination, overwrite)
            future_to_job[future] = (
                reception,
                file_type,
                destination,
            )
        for future in as_completed(future_to_job):
            reception, file_type, destination = future_to_job[future]
            try:
                result = future.result()
            except Exception as exc:
                result = DownloadResult("failed", destination, error=str(exc))
            results.append((reception, file_type, result))
    except KeyboardInterrupt:
        for future in future_to_job:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    except BaseException:
        executor.shutdown(wait=True)
        raise
    else:
        executor.shutdown(wait=True)
    return results
