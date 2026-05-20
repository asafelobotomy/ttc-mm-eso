"""Install TTC data files into the ESO AddOns directory.

Mode A: copy data files into an existing TamrielTradeCentre/ addon folder.
Mode B: create / refresh a lightweight compat addon in AddOns/TamrielTradeCentre/.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

# Bundled compat Lua sources (relative to this file).
_COMPAT_SRC_DIR = Path(__file__).parent / "compat"
_COMPAT_LUA_FILES = ("Init.lua", "Price.lua", "Bootstrap.lua")
_COMPAT_MARKER = "_ttc_mm_compat"


class InstallerError(Exception):
    """Raised when file installation fails."""


def _remove_file_if_present(dest: Path, *, dry_run: bool = False) -> str | None:
    """Delete *dest* when present and return a short action label."""
    if not dest.exists():
        return None
    if dry_run:
        return "would remove stale file"
    try:
        dest.unlink()
    except OSError as exc:
        raise InstallerError(f"Failed to remove {dest.name}: {exc}") from exc
    return "removed stale file"


def _atomic_write(dest: Path, data: bytes, *, backup_suffix: str = "") -> str:
    """Write *data* to *dest* atomically via a temp file + os.replace().

    If *dest* already exists and the content matches, returns ``"unchanged"``
    and skips the write.  Otherwise backs up the old file when *backup_suffix*
    is provided and returns a short action description.

    Raises :exc:`InstallerError` on I/O failure.
    """
    if dest.exists():
        if dest.read_bytes() == data:
            return "unchanged"
        if backup_suffix:
            backup = dest.with_suffix(dest.suffix + backup_suffix)
            shutil.copy2(dest, backup)
            action = f"updated (backup: {backup.name})"
        else:
            action = "updated"
    else:
        action = "installed"

    tmp_fd, tmp_path = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.tmp-")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, dest)
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise InstallerError(f"Failed to write {dest.name}: {exc}") from exc

    return action


def install_mode_a(
    ttc_dir: Path,
    extracted: dict[str, Path],
    *,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Copy extracted data files into the existing *ttc_dir*.

    Returns a list of ``(filename, action)`` pairs.
    """
    results: list[tuple[str, str]] = []
    backup_suffix = f".ttc-mm-{date.today():%Y%m%d}.bak"

    for filename, src_path in extracted.items():
        dest = ttc_dir / filename
        if dry_run:
            results.append((filename, "would update"))
            continue
        action = _atomic_write(dest, src_path.read_bytes(), backup_suffix=backup_suffix)
        results.append((filename, action))

    target_region = None
    if "PriceTableEU.lua" in extracted:
        target_region = "EU"
    elif "PriceTableNA.lua" in extracted:
        target_region = "NA"
    if target_region is not None:
        stale_region = "NA" if target_region == "EU" else "EU"
        stale_file = ttc_dir / f"PriceTable{stale_region}.lua"
        action = _remove_file_if_present(stale_file, dry_run=dry_run)
        if action is not None:
            results.append((stale_file.name, action))

    return results


def install_mode_b(
    addons_root: Path,
    extracted: dict[str, Path],
    region: str,
    locale: str = "EN",
    *,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Create or refresh the compat TamrielTradeCentre addon under *addons_root*.

    Writes the bundled Lua logic files, the downloaded data files, a generated
    ``TamrielTradeCentre.txt`` manifest, and a compat marker file.

    Returns a list of ``(filename, action)`` pairs.
    """
    region = region.upper()
    locale = locale.upper()
    ttc_dir = addons_root / "TamrielTradeCentre"
    results: list[tuple[str, str]] = []
    backup_suffix = f".ttc-mm-{date.today():%Y%m%d}.bak"

    if not dry_run:
        ttc_dir.mkdir(exist_ok=True)

    # --- Static compat Lua logic files -----------------------------------
    for lua_name in _COMPAT_LUA_FILES:
        if dry_run:
            results.append((lua_name, "would install"))
            continue
        src = _COMPAT_SRC_DIR / lua_name
        action = _atomic_write(ttc_dir / lua_name, src.read_bytes(), backup_suffix=backup_suffix)
        results.append((lua_name, action))

    # --- Downloaded data files -------------------------------------------
    for filename, src_path in extracted.items():
        if dry_run:
            results.append((filename, "would install"))
            continue
        action = _atomic_write(ttc_dir / filename, src_path.read_bytes(), backup_suffix=backup_suffix)
        results.append((filename, action))

    stale_region = "NA" if region == "EU" else "EU"
    stale_file = ttc_dir / f"PriceTable{stale_region}.lua"
    action = _remove_file_if_present(stale_file, dry_run=dry_run)
    if action is not None:
        results.append((stale_file.name, action))

    # --- Addon manifest (TamrielTradeCentre.txt) -------------------------
    price_table_file = f"PriceTable{region}.lua"
    manifest_entries = ["Init.lua", price_table_file, "ItemLookUpTable_EN.lua"]
    if locale != "EN":
        locale_file = f"ItemLookUpTable_{locale}.lua"
        if locale_file in extracted or (not dry_run and (ttc_dir / locale_file).exists()):
            manifest_entries.append(locale_file)
    manifest_entries.extend(["Price.lua", "Bootstrap.lua"])

    manifest_text = (
        "## APIVersion: 101049\n"
        "## Title: Tamriel Trade Centre (ttc-mm compat)\n"
        "## AddOnVersion: 1\n"
        "\n"
        + "\n".join(manifest_entries)
        + "\n"
    )

    if dry_run:
        results.append(("TamrielTradeCentre.txt", "would generate"))
        results.append((_COMPAT_MARKER, "would write"))
    else:
        action = _atomic_write(ttc_dir / "TamrielTradeCentre.txt", manifest_text.encode("utf-8"))
        results.append(("TamrielTradeCentre.txt", action))
        action = _atomic_write(
            ttc_dir / _COMPAT_MARKER,
            b"Generated by ttc-mm. Do not delete this file.\n",
        )
        results.append((_COMPAT_MARKER, action))

    return results
