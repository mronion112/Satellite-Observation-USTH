"""Fetch reception pages and extract UTC timestamps and data links."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import Mapping
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from config import REQUEST_TIMEOUT

DATA_TYPE_FILENAMES: Mapping[str, str] = {
    "CADU": "file.cadu",
    "Telemetry JSON": "telemetry.json",
    "Dataset JSON": "dataset.json",
    "Product CBOR": "product.cbor",
}


@dataclass
class Reception:
    """Data and parsing issues extracted from one reception section."""

    index: int
    timestamp: datetime | None
    timestamp_text: str | None
    links: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def missing_types(self) -> list[str]:
        """Return expected file types for which this section has no URL."""
        return [file_type for file_type in DATA_TYPE_FILENAMES if file_type not in self.links]


def fetch_html(url: str) -> str:
    """Fetch a page and return its decoded HTML, raising on HTTP failures."""
    with requests.get(url, timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        return response.text


def fetch_document(url: str) -> bytes:
    """Fetch the full HTML document as its original response bytes."""
    with requests.get(url, timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        return response.content


def save_html_document(
    document: bytes,
    destination: str | Path,
    overwrite: bool = False,
) -> bool:
    """Save a complete HTML document atomically without clobbering by default.

    Return ``True`` when saved and ``False`` when an existing file was skipped.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        if destination.is_file():
            return False
        raise OSError(f"destination exists and is not a file: {destination}")

    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as output_file:
            output_file.write(document)
        if overwrite:
            os.replace(temporary_path, destination)
        else:
            try:
                os.link(temporary_path, destination)
            except FileExistsError:
                return False
        return True
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


def extract_reception_time(section: Tag) -> datetime:
    """Extract the explicitly labeled UTC reception time from a section."""
    time_container = section.find("div", class_="reception-time")
    if not isinstance(time_container, Tag):
        raise ValueError("missing reception-time element")

    expected_label = "Reception Time (UTC)"
    for row in time_container.find_all("div"):
        strong = row.find("strong")
        if not isinstance(strong, Tag):
            continue
        label = " ".join(strong.get_text(" ", strip=True).split())
        if label.rstrip(":").casefold() != expected_label.casefold():
            continue

        row_text = " ".join(row.get_text(" ", strip=True).split())
        timestamp_text = row_text[len(label) :].lstrip(" :")
        if not timestamp_text:
            raise ValueError("Reception Time (UTC) value is empty")
        try:
            parsed = datetime.strptime(timestamp_text, "%Y/%m/%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(
                f"invalid Reception Time (UTC) value {timestamp_text!r}; "
                "expected YYYY/MM/DD HH:MM:SS"
            ) from exc
        return parsed.replace(tzinfo=timezone.utc)

    raise ValueError("Reception Time (UTC) field not found")


def _identify_data_type(label: str) -> str | None:
    """Map a card's strong label to one of the supported file types."""
    normalized = " ".join(label.casefold().split())
    if "cadu" in normalized:
        return "CADU"
    if "telemetry" in normalized and "json" in normalized:
        return "Telemetry JSON"
    if "dataset" in normalized and "json" in normalized:
        return "Dataset JSON"
    if "product" in normalized and "cbor" in normalized:
        return "Product CBOR"
    return None


def extract_download_links(section: Tag) -> dict[str, str]:
    """Extract supported data-card links scoped to a single reception."""
    links: dict[str, str] = {}
    for card in section.find_all("a", class_="data-card"):
        strong = card.find("strong")
        href = card.get("href")
        if not isinstance(strong, Tag) or not isinstance(href, str) or not href.strip():
            continue
        file_type = _identify_data_type(strong.get_text(" ", strip=True))
        if file_type and file_type not in links:
            links[file_type] = href.strip()
    return links


def parse_receptions(html: str | bytes, base_url: str | None = None) -> list[Reception]:
    """Parse every reception section, keeping timestamp errors reportable."""
    soup = BeautifulSoup(html, "html.parser")
    sections = soup.find_all("section", class_="reception")
    receptions: list[Reception] = []

    for index, section in enumerate(sections, start=1):
        links = extract_download_links(section)
        if base_url:
            links = {file_type: urljoin(base_url, href) for file_type, href in links.items()}

        timestamp: datetime | None = None
        timestamp_text: str | None = None
        errors: list[str] = []
        try:
            timestamp = extract_reception_time(section)
            timestamp_text = timestamp.strftime("%Y/%m/%d %H:%M:%S")
        except ValueError as exc:
            errors.append(str(exc))

        receptions.append(
            Reception(
                index=index,
                timestamp=timestamp,
                timestamp_text=timestamp_text,
                links=links,
                errors=errors,
            )
        )
    return receptions


def build_reception_directory(timestamp: datetime, output_dir: str | Path) -> Path:
    """Create and return the output directory for a UTC reception timestamp."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)
    destination = (
        Path(output_dir)
        / timestamp.strftime("%Y")
        / timestamp.strftime("%m")
        / timestamp.strftime("%d_%H-%M-%S")
    )
    destination.mkdir(parents=True, exist_ok=True)
    return destination
