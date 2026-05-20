"""CLI entry point for ttc-mm.

Commands
--------
ttc-mm convert   Interactive full flow: download TTC data, install, optionally patch MM.
ttc-mm validate  Check installed TTC data files and MM patch state.
ttc-mm status    Non-destructive summary of installed mode, file timestamps, and settings.
"""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn


# ---------------------------------------------------------------------------
# Interactive prompt helpers
# ---------------------------------------------------------------------------

def _prompt_choice(message: str, choices: list[str]) -> str:
    """Prompt the user to choose from a list of options (case-insensitive)."""
    choices_upper = [c.upper() for c in choices]
    display = "/".join(choices)
    while True:
        try:
            answer = input(f"{message} [{display}]: ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print()
            _die("Aborted.")
        if answer in choices_upper:
            return answer
        print(f"  Please enter one of: {display}")


def _prompt_path(message: str) -> str:
    """Prompt the user for a filesystem path."""
    while True:
        try:
            answer = input(f"{message}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            _die("Aborted.")
        if answer:
            return answer
        print("  Path cannot be empty.")


def _die(message: str, code: int = 1) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Subcommand implementations (delegating to modules filled in later phases)
# ---------------------------------------------------------------------------

def _cmd_convert(args: argparse.Namespace) -> None:
    # --- Resolve region --------------------------------------------------
    region: str = args.region or _prompt_choice("Region", ["EU", "NA"])

    # --- Resolve AddOns path ---------------------------------------------
    raw_path: str = args.addons_path or _prompt_path(
        "Path to your ESO AddOns directory (or MasterMerchant folder)"
    )

    # --- Path resolution (Phase 3) ---------------------------------------
    from ttc_mm.path_resolver import resolve_paths, PathResolverError
    try:
        paths = resolve_paths(raw_path)
    except PathResolverError as exc:
        _die(str(exc))

    print(f"  AddOns root : {paths.addons_root}")
    print(f"  Install mode: {'A (official TTC addon)' if paths.install_mode == 'A' else 'B (compat addon)'}")
    if paths.saved_variables_dir:
        print(f"  SavedVars   : {paths.saved_variables_dir}")
    else:
        print("  SavedVars   : not found (MM patch step will be skipped)")
    print()

    # --- Download + extract (Phase 2) ------------------------------------
    from ttc_mm.downloader import download_price_table, DownloadError, ExtractError
    print(f"Downloading TTC price table ({region})…")
    if args.dry_run:
        print("  [dry-run] would download and extract files")
        extracted: dict = {}
    else:
        try:
            extracted = download_price_table(
                region,
                locale=args.locale,
            )
        except DownloadError as exc:
            _die(f"Download failed: {exc}")
        except ExtractError as exc:
            _die(f"Extraction failed: {exc}")
        for name, path in extracted.items():
            print(f"  extracted: {name}")
    print()

    # --- Install (Phase 4 / 5) -------------------------------------------
    from ttc_mm.installer import install_mode_a, install_mode_b, InstallerError
    print("Installing TTC data…")
    if args.dry_run:
        print("  [dry-run] would install files")
    else:
        try:
            if paths.install_mode == "A":
                results = install_mode_a(paths.ttc_dir, extracted)
            else:
                results = install_mode_b(paths.addons_root, extracted, region, args.locale)
        except InstallerError as exc:
            _die(f"Install failed: {exc}")
        for filename, action in results:
            print(f"  {action}: {filename}")
    print()

    # --- Optional MM patch (Phase 6) -------------------------------------
    if args.no_patch:
        print("Skipping MM saved-variables patch (--no-patch).")
        return

    if not paths.saved_variables_dir:
        print("Skipping MM saved-variables patch (SavedVariables directory not found).")
        return

    sv_path = paths.saved_variables_dir / "ShopkeeperSavedVars.lua"
    if not sv_path.exists():
        print("Skipping MM saved-variables patch (ShopkeeperSavedVars.lua not found).")
        print("  This is normal if ESO has never been launched with Master Merchant.")
        return

    from ttc_mm.patcher import offer_patch, PatcherError
    try:
        offer_patch(sv_path, dry_run=args.dry_run)
    except PatcherError as exc:
        _die(f"Patch failed: {exc}")


def _cmd_validate(args: argparse.Namespace) -> None:
    raw_path: str = args.addons_path or _prompt_path(
        "Path to your ESO AddOns directory (or MasterMerchant folder)"
    )

    from ttc_mm.path_resolver import resolve_paths, PathResolverError
    try:
        paths = resolve_paths(raw_path)
    except PathResolverError as exc:
        _die(str(exc))

    from ttc_mm.validator import run_validate
    exit_code = run_validate(paths)
    sys.exit(exit_code)


def _cmd_status(args: argparse.Namespace) -> None:
    raw_path: str = args.addons_path or _prompt_path(
        "Path to your ESO AddOns directory (or MasterMerchant folder)"
    )

    from ttc_mm.path_resolver import resolve_paths, PathResolverError
    try:
        paths = resolve_paths(raw_path)
    except PathResolverError as exc:
        _die(str(exc))

    from ttc_mm.validator import run_status
    run_status(paths)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ttc-mm",
        description=(
            "Download Tamriel Trade Centre price-table data and install it so "
            "Master Merchant can use TTC as a pricing source."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_version()}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # -- convert -----------------------------------------------------------
    p_convert = subparsers.add_parser(
        "convert",
        help="Download TTC data, install it, and optionally patch MM settings.",
        description=(
            "Downloads the TTC price table for the chosen region, installs it "
            "into the ESO AddOns directory, and optionally updates Master "
            "Merchant saved-variable defaults to prefer TTC pricing."
        ),
    )
    p_convert.add_argument(
        "--region",
        choices=["EU", "NA"],
        metavar="REGION",
        help="Server region: EU or NA. Prompted interactively if omitted.",
    )
    p_convert.add_argument(
        "--addons-path",
        metavar="PATH",
        help=(
            "Path to your ESO AddOns directory or to the MasterMerchant folder "
            "inside it. Prompted interactively if omitted."
        ),
    )
    p_convert.add_argument(
        "--locale",
        default="EN",
        choices=["EN", "DE", "FR", "RU", "ZH", "ES", "JP"],
        metavar="LOCALE",
        help="Item-lookup-table locale to install in addition to EN (default: EN).",
    )
    p_convert.add_argument(
        "--no-patch",
        action="store_true",
        help="Skip the optional Master Merchant saved-variables patch step.",
    )
    p_convert.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without writing any files.",
    )

    # -- validate ----------------------------------------------------------
    p_validate = subparsers.add_parser(
        "validate",
        help="Check that installed TTC data files are present and valid.",
        description=(
            "Verifies that TTC price-table and lookup files are installed, "
            "reports the install mode (A = official addon, B = compat), and "
            "checks which Master Merchant TTC settings are currently patched."
        ),
    )
    p_validate.add_argument(
        "--addons-path",
        metavar="PATH",
        help="Path to your ESO AddOns directory or MasterMerchant folder.",
    )

    # -- status ------------------------------------------------------------
    p_status = subparsers.add_parser(
        "status",
        help="Non-destructive summary of install mode, file timestamps, and MM settings.",
        description=(
            "Prints a summary of the current TTC installation state without "
            "making any changes."
        ),
    )
    p_status.add_argument(
        "--addons-path",
        metavar="PATH",
        help="Path to your ESO AddOns directory or MasterMerchant folder.",
    )

    return parser


def _version() -> str:
    from ttc_mm import __version__
    return __version__


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "convert":
        _cmd_convert(args)
    elif args.command == "validate":
        _cmd_validate(args)
    elif args.command == "status":
        _cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
