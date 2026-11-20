"""Command-line entry point for the satellite reception scraper."""

from __future__ import annotations

from pathlib import Path

from config import HTML_FILENAME, MAX_DOWNLOAD_WORKERS, OUTPUT_DIR, OVERWRITE, TARGET_URL
from downloader import DownloadResult, download_receptions_files
from scraper import (
    Reception,
    build_reception_directory,
    fetch_document,
    parse_receptions,
    save_html_document,
)


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _print_result(
    reception: Reception,
    file_type: str,
    result: DownloadResult,
    completed: int,
    total: int,
) -> tuple[int, int, int]:
    filename = result.destination.name
    label = f"{reception.timestamp_text or 'reception'} {file_type} -> {filename}"
    if result.status == "downloaded":
        print(
            f"[SUCCESS] [{completed}/{total}] {label} "
            f"({_format_size(result.bytes_downloaded)})"
        )
        return 1, 0, 0
    if result.status == "skipped":
        print(f"[SKIPPED] [{completed}/{total}] {label}: {result.error}")
        return 0, 0, 1
    print(f"[ERROR] [{completed}/{total}] {label}: {result.error}")
    return 0, 1, 0


def _report_reception(reception: Reception, output_dir: str) -> None:
    print(f"\n[RECEPTION] {reception.timestamp_text or 'invalid UTC timestamp'}")
    for error in reception.errors:
        print(f"[ERROR] Reception {reception.index}: {error}")

    for file_type in reception.missing_types:
        print(f"[MISSING] {file_type} link not found")

    if reception.timestamp is not None:
        reception_dir = build_reception_directory(reception.timestamp, output_dir)
        print(f"[INFO] Reception directory: {reception_dir}")


def run(
    target_url: str,
    output_dir: str,
    overwrite: bool = OVERWRITE,
) -> int:
    """Save the source HTML and download every linked reception file."""
    print("[INFO] Fetching webpage...")
    try:
        document = fetch_document(target_url)
        document_path = Path(output_dir) / HTML_FILENAME
        saved = save_html_document(document, document_path, overwrite=overwrite)
    except Exception as exc:
        print(f"[ERROR] Unable to fetch or save {target_url}: {exc}")
        return 1

    if saved:
        print(f"[SUCCESS] Saved HTML document: {document_path} ({_format_size(len(document))})")
    else:
        print(f"[SKIPPED] HTML document already exists: {document_path}")

    receptions = parse_receptions(document, base_url=target_url)
    print(f"[INFO] Found {len(receptions)} reception sections.")
    for reception in receptions:
        _report_reception(reception, output_dir)

    file_count = sum(
        len(reception.links) for reception in receptions if reception.timestamp is not None
    )
    print(
        f"\n[INFO] Downloading {file_count} files with "
        f"up to {MAX_DOWNLOAD_WORKERS} threads; existing files will be skipped."
    )
    results = download_receptions_files(
        receptions,
        output_dir,
        overwrite=overwrite,
        max_workers=MAX_DOWNLOAD_WORKERS,
    )
    downloaded = failed = skipped = 0
    for completed, (reception, file_type, result) in enumerate(results, start=1):
        counts = _print_result(reception, file_type, result, completed, len(results))
        downloaded += counts[0]
        failed += counts[1]
        skipped += counts[2]

    invalid_timestamps = sum(reception.timestamp is None for reception in receptions)
    missing_links = sum(len(reception.missing_types) for reception in receptions)
    print("\n[SUMMARY]")
    print(f"Receptions found: {len(receptions)}")
    print(f"Files downloaded: {downloaded}")
    print(f"Failed downloads: {failed}")
    print(f"Skipped existing files: {skipped}")
    print(f"Invalid timestamps: {invalid_timestamps}")
    print(f"Missing links: {missing_links}")
    return 1 if failed or invalid_timestamps or missing_links else 0


def main() -> int:
    try:
        return run(TARGET_URL, OUTPUT_DIR, OVERWRITE)
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted. Completed files are kept; rerun to resume.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
