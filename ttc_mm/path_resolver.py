"""Resolve ESO AddOns paths, detect install mode, and locate SavedVariables."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Marker file written into AddOns/TamrielTradeCentre/ by the Mode B installer.
COMPAT_MARKER = "_ttc_mm_compat"

# String present in the official TTC addon manifest but absent from the compat one.
_OFFICIAL_TTC_MARKER = "DependsOn: LibAddonMenu-2.0"


class PathResolverError(Exception):
    """Raised when the supplied path cannot be resolved to a valid AddOns tree."""


@dataclass
class ResolvedPaths:
    addons_root: Path
    master_merchant_dir: Path | None
    ttc_dir: Path | None          # None only when TamrielTradeCentre/ is absent (new Mode B)
    saved_variables_dir: Path | None
    install_mode: Literal["A", "B"]
    is_compat_install: bool       # True when ttc_dir was created by ttc-mm


def _is_official_ttc(ttc_dir: Path) -> bool:
    """Return True if *ttc_dir* contains an official TTC addon manifest."""
    manifest = ttc_dir / "TamrielTradeCentre.txt"
    if not manifest.exists():
        return False
    try:
        return _OFFICIAL_TTC_MARKER in manifest.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _find_addons_root(start: Path) -> Path:
    """Walk up from *start* to find the first directory containing MasterMerchant/.

    Also probes one ``AddOns/`` subdirectory level so the user can supply the
    ``live/`` ESO directory or any ancestor.
    """
    candidate = start
    while True:
        if (candidate / "MasterMerchant").is_dir():
            return candidate
        addons_sub = candidate / "AddOns"
        if addons_sub.is_dir() and (addons_sub / "MasterMerchant").is_dir():
            return addons_sub
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    raise PathResolverError(
        f"Cannot find MasterMerchant addon at or above: {start}\n"
        "Supply your ESO AddOns directory or the MasterMerchant folder inside it."
    )


def _find_saved_variables(addons_root: Path) -> Path | None:
    """Walk up from *addons_root* to find a ``live/`` directory.

    Returns ``live/SavedVariables/`` when found and the directory exists.
    """
    candidate = addons_root
    while True:
        if candidate.name.lower() == "live":
            sv = candidate / "SavedVariables"
            return sv if sv.is_dir() else None
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent


def resolve_paths(supplied: str | Path) -> ResolvedPaths:
    """Resolve *supplied* to a :class:`ResolvedPaths` instance.

    Accepts:
    - a ``MasterMerchant/`` folder path
    - an ``AddOns/`` folder path
    - any ancestor directory that contains an ``AddOns/MasterMerchant/`` subtree
    """
    p = Path(supplied).expanduser().resolve()

    if not p.exists():
        raise PathResolverError(f"Path does not exist: {p}")
    if not p.is_dir():
        raise PathResolverError(f"Path is not a directory: {p}")

    # Shortcut: user passed the MasterMerchant folder itself.
    if p.name == "MasterMerchant" and p.is_dir():
        addons_root = p.parent
    else:
        addons_root = _find_addons_root(p)

    mm_dir = addons_root / "MasterMerchant"
    ttc_candidate = addons_root / "TamrielTradeCentre"

    if ttc_candidate.is_dir():
        ttc_dir: Path | None = ttc_candidate
        is_compat = (ttc_candidate / COMPAT_MARKER).exists()
        is_official = _is_official_ttc(ttc_candidate)
        # Use Mode B (refresh compat Lua + data) when compat marker is present
        # and the official TTC addon has NOT been installed on top of it.
        install_mode: Literal["A", "B"] = "B" if (is_compat and not is_official) else "A"
    else:
        ttc_dir = None
        is_compat = False
        install_mode = "B"

    sv_dir = _find_saved_variables(addons_root)

    return ResolvedPaths(
        addons_root=addons_root,
        master_merchant_dir=mm_dir if mm_dir.is_dir() else None,
        ttc_dir=ttc_dir,
        saved_variables_dir=sv_dir,
        install_mode=install_mode,
        is_compat_install=is_compat,
    )
