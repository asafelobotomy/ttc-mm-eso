"""Download and extract TTC price-table zip files."""

from __future__ import annotations

import os
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

_DOWNLOAD_URLS: dict[str, str] = {
    "EU": "https://eu.tamrieltradecentre.com/download/PriceTable",
    "NA": "https://us.tamrieltradecentre.com/download/PriceTable",
}

_USER_AGENT = "ttc-mm/0.1 (+https://github.com/ttc-mm-eso)"

_PRICE_TABLE_FILE: dict[str, str] = {
    "EU": "PriceTableEU.lua",
    "NA": "PriceTableNA.lua",
}


class DownloadError(Exception):
    """Raised when the HTTP download fails."""


class ExtractError(Exception):
    """Raised when the downloaded archive cannot be extracted."""


def download_price_table(
    region: str,
    *,
    locale: str = "EN",
    timeout: int = 60,
    dry_run: bool = False,
) -> dict[str, Path]:
    """Download and extract the TTC price table for *region*.

    Returns a dict mapping logical file names to temporary extracted paths,
    e.g. ``{"PriceTableNA.lua": Path("/tmp/ttc-mm-extract-.../PriceTableNA.lua"), ...}``.
    The caller owns the temporary directory; it persists until process exit.
    """
    region = region.upper()
    locale = locale.upper()

    url = _DOWNLOAD_URLS.get(region)
    if url is None:
        raise DownloadError(f"Unknown region: {region!r}. Valid values: EU, NA")

    if dry_run:
        return {}

    price_table_name = _PRICE_TABLE_FILE[region]
    required_names: set[str] = {price_table_name, "ItemLookUpTable_EN.lua"}
    optional_names: set[str] = set()
    if locale != "EN":
        optional_names.add(f"ItemLookUpTable_{locale}.lua")

    tmp_zip: str | None = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                tmp_fd, tmp_zip = tempfile.mkstemp(suffix=".zip", prefix="ttc-mm-dl-")
                with os.fdopen(tmp_fd, "wb") as f:
                    while chunk := resp.read(65536):
                        f.write(chunk)
        except urllib.error.HTTPError as exc:
            msg = f"HTTP {exc.code} downloading from {url}"
            if exc.code == 403:
                msg += " — access forbidden (TTC may require a newer client)"
            elif exc.code == 404:
                msg += " — not found (TTC server may be down)"
            elif exc.code == 429:
                retry_after = exc.headers.get("Retry-After", "unknown")
                msg += f" — rate limited (Retry-After: {retry_after}s)"
            elif exc.code >= 500:
                msg += " — server error; try again later"
            raise DownloadError(msg) from exc
        except urllib.error.URLError as exc:
            raise DownloadError(f"Network error: {exc.reason}") from exc
        except TimeoutError:
            raise DownloadError(f"Download timed out after {timeout}s")

        if not zipfile.is_zipfile(tmp_zip):
            raise ExtractError(f"Response from {url} is not a valid zip archive")

        out_dir = tempfile.mkdtemp(prefix="ttc-mm-extract-")
        extracted: dict[str, Path] = {}

        with zipfile.ZipFile(tmp_zip, "r") as zf:
            # Map basename → member path (ignores any directory prefix in the zip).
            entries: dict[str, str] = {}
            for info in zf.infolist():
                if not info.is_dir():
                    entries[Path(info.filename).name] = info.filename

            missing = required_names - entries.keys()
            if missing:
                raise ExtractError(
                    "Required file(s) not found in downloaded zip: "
                    + ", ".join(sorted(missing))
                )

            for target in required_names | optional_names:
                if target not in entries:
                    continue
                out_path = Path(out_dir) / target
                out_path.write_bytes(zf.read(entries[target]))
                extracted[target] = out_path

        if locale != "EN" and f"ItemLookUpTable_{locale}.lua" not in extracted:
            print(
                f"  warning: ItemLookUpTable_{locale}.lua not in downloaded zip;"
                " only EN lookup table installed.",
                file=sys.stderr,
            )

        return extracted
    finally:
        if tmp_zip and os.path.exists(tmp_zip):
            try:
                os.unlink(tmp_zip)
            except OSError:
                pass
