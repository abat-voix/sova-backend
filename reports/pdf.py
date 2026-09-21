from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import requests
from django.conf import settings


HTML_CONVERSION_PATH = "/forms/chromium/convert/html"
DEFAULT_FORM_FIELDS: dict[str, str] = {
    "paperWidth": "8.27in",
    "paperHeight": "11.7in",
    "marginTop": "0",
    "marginBottom": "0",
    "marginLeft": "0",
    "marginRight": "0",
    "preferCssPageSize": "true",
    "printBackground": "true",
    "failOnResourceLoadingFailed": "true",
}


class PDFGenerationError(RuntimeError):
    """Raised when Gotenberg cannot produce a valid PDF."""


@dataclass(frozen=True, slots=True)
class HTMLAsset:
    """A CSS, image, or font file referenced by the report HTML."""

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        reserved_filenames = {"index.html", "header.html", "footer.html"}
        if not self.filename or self.filename in reserved_filenames:
            raise ValueError(f"Reserved or empty asset filename: {self.filename!r}")
        if (
            self.filename.startswith("/")
            or "\\" in self.filename
            or ".." in self.filename.split("/")
        ):
            raise ValueError(f"Asset filename must be relative: {self.filename!r}")


def html_to_pdf(
    html: str | bytes,
    *,
    assets: tuple[HTMLAsset, ...] = (),
    header_html: str | bytes | None = None,
    footer_html: str | bytes | None = None,
    output_filename: str | None = None,
    form_fields: Mapping[str, str | int | float | bool] | None = None,
) -> bytes:
    """Convert a complete HTML document and its local assets to PDF."""

    asset_filenames = [asset.filename for asset in assets]
    if len(asset_filenames) != len(set(asset_filenames)):
        raise ValueError("Asset filenames must be unique.")
    if output_filename and any(
        character in output_filename for character in "/\\\r\n"
    ):
        raise ValueError("Output filename must not contain path separators.")

    files: list[tuple[str, tuple[str, str | bytes, str]]] = [
        ("files", ("index.html", html, "text/html; charset=utf-8"))
    ]
    if header_html is not None:
        files.append(
            ("files", ("header.html", header_html, "text/html; charset=utf-8"))
        )
    if footer_html is not None:
        files.append(
            ("files", ("footer.html", footer_html, "text/html; charset=utf-8"))
        )
    files.extend(
        ("files", (asset.filename, asset.content, asset.content_type))
        for asset in assets
    )

    data = dict(DEFAULT_FORM_FIELDS)
    if form_fields:
        data.update(
            {
                name: _serialize_form_value(value)
                for name, value in form_fields.items()
            }
        )

    headers = {}
    if output_filename:
        headers["Gotenberg-Output-Filename"] = output_filename

    try:
        response = requests.post(
            f"{settings.GOTENBERG_URL}{HTML_CONVERSION_PATH}",
            files=files,
            data=data,
            headers=headers,
            timeout=settings.GOTENBERG_TIMEOUT,
        )
    except requests.RequestException as error:
        raise PDFGenerationError("Could not connect to Gotenberg.") from error

    if response.status_code != 200:
        details = response.text.strip()[:500]
        suffix = f": {details}" if details else ""
        raise PDFGenerationError(
            f"Gotenberg returned HTTP {response.status_code}{suffix}"
        )

    if not response.content.startswith(b"%PDF-"):
        raise PDFGenerationError("Gotenberg returned a response that is not a PDF.")

    return response.content


def _serialize_form_value(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
