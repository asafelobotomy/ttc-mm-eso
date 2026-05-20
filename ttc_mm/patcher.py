"""Read and patch Master Merchant saved-variable settings related to TTC."""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


class PatcherError(Exception):
    """Raised when a saved-variable patch operation fails."""


SAVED_VARS_FILENAMES = ("MasterMerchant.lua", "ShopkeeperSavedVars.lua")


# MM_PRICE_* integer constants from MasterMerchant_Namespace_Init.lua.
MM_PRICE_TTC_SUGGESTED = 1
MM_PRICE_TTC_AVERAGE = 2
MM_PRICE_MM_AVERAGE = 3
MM_PRICE_BONANZA = 4
MM_PRICE_TTC_SALES = 5

# Human-readable labels for the integer pricing modes.
PRICE_MODE_LABELS: dict[int, str] = {
    MM_PRICE_TTC_SUGGESTED: "TTC Suggested price",
    MM_PRICE_TTC_AVERAGE:   "TTC Average price",
    MM_PRICE_MM_AVERAGE:    "MM Average (guild history)",
    MM_PRICE_BONANZA:       "Bonanza price",
    MM_PRICE_TTC_SALES:     "TTC Sales Average",
}

# Patch targets: setting name → (type, suggested default)
# Numeric settings use the integer MM_PRICE_* constants stored in SavedVars.
PATCH_TARGETS: dict[str, tuple[type, object]] = {
    "showTTCTipline":            (bool, True),
    "showTTCSalesAverage":       (bool, False),
    "includeTTCDataPriceToChat": (bool, True),
    "dealCalcToUse":             (int,  MM_PRICE_TTC_SUGGESTED),
    "replacementTypeToUse":      (int,  MM_PRICE_TTC_SUGGESTED),
    "voucherValueTypeToUse":     (int,  MM_PRICE_TTC_SUGGESTED),
    "agsSalePriceToUse":         (int,  MM_PRICE_TTC_SUGGESTED),
}


def _read_value(content: str, key: str) -> object | None:
    """Extract the raw Lua value for *key* from saved-var file content."""
    m = re.search(r'\["' + re.escape(key) + r'"\]\s*=\s*(\w+)', content)
    if not m:
        return None
    raw = m.group(1)
    if raw == "true":
        return True
    if raw == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        return raw


def _patch_value(content: str, key: str, new_value: object) -> str:
    """Replace the stored value for *key* in Lua saved-var content.

    Raises :exc:`PatcherError` when the key is not found.
    """
    if isinstance(new_value, bool):
        lua_val = "true" if new_value else "false"
    elif isinstance(new_value, int):
        lua_val = str(new_value)
    else:
        lua_val = f'"{new_value}"'

    pattern = re.compile(r'(\["' + re.escape(key) + r'"\]\s*=\s*)(\w+)')
    if pattern.search(content) is None:
        raise PatcherError(f"Key {key!r} not found in saved variables file")
    new_content = pattern.sub(lambda m: m.group(1) + lua_val, content)
    return new_content


def read_patch_state(saved_vars_path: Path) -> dict[str, object]:
    """Return the current values of all patch targets from *saved_vars_path*."""
    if not saved_vars_path.exists():
        return {}
    content = saved_vars_path.read_text(encoding="utf-8", errors="ignore")
    return {key: _read_value(content, key) for key in PATCH_TARGETS}


def find_saved_vars_file(saved_variables_dir: Path) -> Path | None:
    """Return the first supported Master Merchant saved vars file in *saved_variables_dir*."""
    for filename in SAVED_VARS_FILENAMES:
        candidate = saved_variables_dir / filename
        if candidate.exists():
            return candidate
    return None


def offer_patch(saved_vars_path: Path, *, dry_run: bool = False) -> None:
    """Interactively offer to patch TTC-related MM saved-variable settings."""
    if not saved_vars_path.exists():
        print("  Master Merchant saved vars file not found — patch step skipped.")
        return

    current = read_patch_state(saved_vars_path)
    _warn_if_eso_running()

    changes: dict[str, object] = {}
    print("  Current MM TTC settings (from your saved variables):")

    for key, (typ, suggested) in PATCH_TARGETS.items():
        cur = current.get(key)
        if typ is bool:
            cur_label = str(cur) if cur is not None else "(not set)"
            if cur == suggested:
                print(f"    {key}: {cur_label}  [already at suggested value]")
                continue
            answer = _ask(f"    Set {key} to {suggested}? [current: {cur_label}] [y/N]: ")
            if answer.lower() == "y":
                changes[key] = suggested
        elif typ is int:
            cur_label = f"{cur} ({PRICE_MODE_LABELS.get(cur, '?')})" if cur is not None else "(not set)"
            print(f"    {key}: {cur_label}")
            _options = [
                (MM_PRICE_TTC_SUGGESTED, "TTC Suggested price (recommended)"),
                (MM_PRICE_TTC_AVERAGE,   "TTC Average price"),
                (MM_PRICE_TTC_SALES,     "TTC Sales Average"),
            ]
            for i, (val, label) in enumerate(_options, 1):
                print(f"      {i}. {label}")
            print(f"      4. Leave unchanged")
            answer = _ask(f"    Choice [1-4, default 4]: ")
            idx_map = {"1": _options[0][0], "2": _options[1][0], "3": _options[2][0]}
            if answer in idx_map:
                changes[key] = idx_map[answer]

    if not changes:
        print("  No changes requested.")
        return

    if dry_run:
        print(f"  [dry-run] would apply {len(changes)} change(s): {changes}")
        return

    backup = backup_saved_vars(saved_vars_path)
    print(f"  Backed up to: {backup.name}")

    content = saved_vars_path.read_text(encoding="utf-8", errors="ignore")
    for key, value in changes.items():
        content = _patch_value(content, key, value)
    saved_vars_path.write_text(content, encoding="utf-8")
    print(f"  Applied {len(changes)} change(s).")


def backup_saved_vars(saved_vars_path: Path) -> Path:
    """Copy *saved_vars_path* to a timestamped backup.  Returns the backup path."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = saved_vars_path.with_suffix(f".ttc-mm-{ts}.bak")
    shutil.copy2(saved_vars_path, backup)
    return backup


def restore_backup(backup_path: Path) -> None:
    """Restore a backup produced by :func:`backup_saved_vars`."""
    if not backup_path.exists():
        raise PatcherError(f"Backup not found: {backup_path}")
    original_name = re.sub(r"\.ttc-mm-\d{8}-\d{6}\.bak$", "", backup_path.name)
    original = backup_path.parent / original_name
    shutil.copy2(backup_path, original)
    backup_path.unlink()


def _ask(prompt: str) -> str:
    """Read a line from stdin, returning empty string on EOF/interrupt."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _warn_if_eso_running() -> None:
    """Print a warning if an ESO process is detected."""
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-f", "eso64"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            print(
                "  Warning: ESO appears to be running. Patches may be overwritten\n"
                "  when ESO saves on logout. Consider patching after closing the game.",
                file=sys.stderr,
            )
    except (FileNotFoundError, OSError):
        pass
