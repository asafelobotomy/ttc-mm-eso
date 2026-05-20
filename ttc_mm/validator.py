"""Validate installed TTC data and report installation status."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from ttc_mm.path_resolver import ResolvedPaths


def run_validate(paths: ResolvedPaths) -> int:
    """Check that TTC data files are installed and valid.

    Prints a human-readable report and returns an exit code:
    - 0: all checks pass
    - 1: warnings (e.g. data is more than 3 days old)
    - 2: errors (e.g. required files missing)
    """
    errors = 0
    warnings = 0

    # --- Install mode ---------------------------------------------------
    if paths.ttc_dir is None:
        print("ERROR: TamrielTradeCentre addon directory not found.")
        print(f"  Expected: {paths.addons_root / 'TamrielTradeCentre'}")
        print("  Run `ttc-mm convert` to install.")
        return 2

    if paths.is_compat_install:
        # Detect official TTC installed on top of compat addon (conflict).
        manifest = paths.ttc_dir / "TamrielTradeCentre.txt"
        if manifest.exists():
            content = manifest.read_text(encoding="utf-8", errors="ignore")
            if "DependsOn: LibAddonMenu-2.0" in content:
                print(
                    "WARNING: Official TTC addon detected alongside the ttc-mm\n"
                    "  compat marker. Run `ttc-mm convert` to update, or remove\n"
                    "  the compat files if you installed official TTC via Minion."
                )
                warnings += 1
        mode_label = "B (ttc-mm compat)"
    else:
        mode_label = "A (official TTC addon)"

    print(f"Install mode  : {mode_label}")
    print(f"TTC dir       : {paths.ttc_dir}")

    # --- Price table files ----------------------------------------------
    found_price_table = False
    for region in ("NA", "EU"):
        price_file = paths.ttc_dir / f"PriceTable{region}.lua"
        if not price_file.exists():
            continue
        found_price_table = True
        size_kb = price_file.stat().st_size // 1024
        ts = _read_timestamp(price_file)
        if ts is not None:
            age_days = (datetime.now(timezone.utc).timestamp() - ts) / 86400
            if age_days > 3:
                print(f"  WARNING: PriceTable{region}.lua is {age_days:.1f} days old ({size_kb} KB) — run convert to refresh")
                warnings += 1
            else:
                print(f"  PriceTable{region}.lua : {size_kb} KB, {age_days:.1f} days old")
        else:
            print(f"  PriceTable{region}.lua : {size_kb} KB (timestamp unreadable)")
            warnings += 1

    if not found_price_table:
        print("ERROR: No PriceTableNA.lua or PriceTableEU.lua found.")
        errors += 1

    # --- Item lookup table ----------------------------------------------
    lookup_file = paths.ttc_dir / "ItemLookUpTable_EN.lua"
    if not lookup_file.exists():
        print("ERROR: ItemLookUpTable_EN.lua missing.")
        errors += 1
    else:
        print(f"  ItemLookUpTable_EN.lua : {lookup_file.stat().st_size // 1024} KB")

    if errors:
        return 2
    if warnings:
        return 1
    return 0


def run_status(paths: ResolvedPaths) -> None:
    """Print a non-destructive summary of install mode, timestamps, and MM settings."""
    print(f"AddOns root   : {paths.addons_root}")
    print(f"MasterMerchant: {'present' if paths.master_merchant_dir else 'NOT FOUND'}")

    if paths.ttc_dir:
        mode = "B (ttc-mm compat)" if paths.is_compat_install else "A (official TTC)"
        print(f"TTC install   : {mode}")
        print(f"TTC dir       : {paths.ttc_dir}")
        for region in ("NA", "EU"):
            price_file = paths.ttc_dir / f"PriceTable{region}.lua"
            if price_file.exists():
                mtime = datetime.fromtimestamp(price_file.stat().st_mtime)
                ts = _read_timestamp(price_file)
                age_str = ""
                if ts is not None:
                    age_days = (datetime.now(timezone.utc).timestamp() - ts) / 86400
                    age_str = f" ({age_days:.1f}d old)"
                print(f"  PriceTable{region}.lua  : modified {mtime:%Y-%m-%d %H:%M}{age_str}")
    else:
        print("TTC install   : not installed (next convert will use Mode B)")

    if paths.saved_variables_dir:
        print(f"SavedVars dir : {paths.saved_variables_dir}")
        from ttc_mm.patcher import (
            read_patch_state,
            PATCH_TARGETS,
            PRICE_MODE_LABELS,
            find_saved_vars_file,
        )
        sv_file = find_saved_vars_file(paths.saved_variables_dir)
        if sv_file is not None:
            print(f"  Using saved vars: {sv_file.name}")
            current = read_patch_state(sv_file)
            print("MM TTC settings:")
            for key, (typ, _suggested) in PATCH_TARGETS.items():
                val = current.get(key)
                if val is None:
                    label = "(not set)"
                elif typ is int:
                    label = f"{val} ({PRICE_MODE_LABELS.get(val, '?')})"
                else:
                    label = str(val)
                print(f"  {key:35s}: {label}")
        else:
            print("  Master Merchant saved vars file not found")
    else:
        print("SavedVars dir : not found")


def _read_timestamp(price_file: Path) -> float | None:
    """Read the ``[\"TimeStamp\"]`` value from a TTC price table Lua file.

    The timestamp is encoded near the end of the file, so only the last 512
    bytes are read.
    """
    pattern = re.compile(r'\["TimeStamp"\]\s*=\s*(\d+)')
    try:
        size = price_file.stat().st_size
        with open(price_file, "rb") as f:
            f.seek(max(0, size - 512))
            tail = f.read().decode("utf-8", errors="ignore")
        m = pattern.search(tail)
        if m:
            return float(m.group(1))
    except OSError:
        pass
    return None
