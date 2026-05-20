"""Simple desktop GUI for ttc-mm."""

from __future__ import annotations

import argparse
import io
import queue
import shutil
import sys
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tkinter as tk
    from tkinter import filedialog, ttk

from ttc_mm import __version__
from ttc_mm.downloader import DownloadError, ExtractError, download_price_table
from ttc_mm.installer import InstallerError, install_mode_a, install_mode_b
from ttc_mm.patcher import (
    MM_PRICE_TTC_AVERAGE,
    MM_PRICE_TTC_SALES,
    MM_PRICE_TTC_SUGGESTED,
    PRICE_MODE_LABELS,
    PatcherError,
    apply_patch_changes,
    build_ttc_patch_changes,
    find_saved_vars_file,
)
from ttc_mm.path_resolver import PathResolverError, resolve_paths
from ttc_mm.validator import run_status, run_validate

REGIONS = ("EU", "NA")
LOCALES = ("EN", "DE", "FR", "RU", "ZH", "ES", "JP")
PATCH_MODE_OPTIONS = {
    "No patch": None,
    f"{PRICE_MODE_LABELS[MM_PRICE_TTC_SUGGESTED]} (recommended)": MM_PRICE_TTC_SUGGESTED,
    PRICE_MODE_LABELS[MM_PRICE_TTC_AVERAGE]: MM_PRICE_TTC_AVERAGE,
    PRICE_MODE_LABELS[MM_PRICE_TTC_SALES]: MM_PRICE_TTC_SALES,
}


def _default_addons_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / "Documents/Elder Scrolls Online/live/AddOns",
        home / ".steam/steam/steamapps/compatdata/306130/pfx/drive_c/users/steamuser/Documents/Elder Scrolls Online/live/AddOns",
    ]


def _find_appimagetool_candidate() -> Path | None:
    build_dir = Path(__file__).resolve().parent.parent / "build"
    for candidate in (
        shutil.which("appimagetool"),
        str(build_dir / "appimagetool-x86_64.AppImage"),
        str(build_dir / "appimagetool-aarch64.AppImage"),
        str(build_dir / "appimagetool.AppImage"),
    ):
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def run_self_check() -> int:
    """Run a lightweight environment check for the GUI/AppImage workflow."""
    failures = 0
    print(f"ttc-mm GUI self-check {__version__}")
    print(f"Python executable: {sys.executable}")

    try:
        _load_tk()
        print("[ok] tkinter runtime is available")
    except ImportError as exc:
        print(f"[fail] tkinter runtime unavailable: {exc}")
        failures += 1

    try:
        import PyInstaller  # noqa: F401
        print("[ok] PyInstaller is available")
    except ImportError as exc:
        print(f"[fail] PyInstaller unavailable: {exc}")
        failures += 1

    appimagetool = _find_appimagetool_candidate()
    if appimagetool is not None:
        print(f"[ok] appimagetool found at {appimagetool}")
    else:
        print("[fail] appimagetool not found in PATH or build/")
        failures += 1

    detected = [candidate for candidate in _default_addons_candidates() if candidate.is_dir()]
    if detected:
        print(f"[ok] default AddOns candidate found: {detected[0]}")
    else:
        print("[warn] no default AddOns path candidate found")

    return 0 if failures == 0 else 1


def _load_tk() -> tuple[Any, Any, Any]:
    """Import tkinter only when the GUI is actually launched."""
    import tkinter as tk_mod
    from tkinter import filedialog as filedialog_mod, ttk as ttk_mod

    return tk_mod, filedialog_mod, ttk_mod


class TtcMmGui:
    """Tkinter desktop wrapper around the existing ttc-mm workflow."""

    def __init__(self, root: Any, *, tk_mod: Any, filedialog_mod: Any, ttk_mod: Any) -> None:
        self.tk = tk_mod
        self.filedialog = filedialog_mod
        self.ttk = ttk_mod
        self.root = root
        self.root.title(f"ttc-mm GUI {__version__}")
        self.root.geometry("920x680")
        self.root.minsize(820, 560)

        self.event_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.addons_path = self.tk.StringVar()
        self.region = self.tk.StringVar(value="EU")
        self.locale = self.tk.StringVar(value="EN")
        self.patch_mode = self.tk.StringVar(value=f"{PRICE_MODE_LABELS[MM_PRICE_TTC_SUGGESTED]} (recommended)")
        self.dry_run = self.tk.BooleanVar(value=False)
        self.status_text = self.tk.StringVar(value="Idle")

        self._configure_style()
        self._build_ui()
        self._prefill_default_path()
        self.root.after(100, self._drain_events)

    def _configure_style(self) -> None:
        style = self.ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except self.tk.TclError:
            pass
        self.root.configure(bg="#eff4ef")
        style.configure("App.TFrame", background="#eff4ef")
        style.configure("Card.TFrame", background="#f9fbf7")
        style.configure("Title.TLabel", background="#eff4ef", font=("TkDefaultFont", 18, "bold"))
        style.configure("Subtitle.TLabel", background="#eff4ef", foreground="#355148")
        style.configure("CardTitle.TLabel", background="#f9fbf7", font=("TkDefaultFont", 10, "bold"))
        style.configure("Run.TButton", padding=(14, 8))

    def _build_ui(self) -> None:
        outer = self.ttk.Frame(self.root, style="App.TFrame", padding=18)
        outer.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = self.ttk.Frame(outer, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        self.ttk.Label(header, text="ttc-mm", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.ttk.Label(
            header,
            text="Desktop wrapper for TTC download, install, validation, and MM pricing patching.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        controls = self.ttk.Frame(outer, style="Card.TFrame", padding=14)
        controls.grid(row=1, column=0, sticky="ew")
        for column in range(4):
            controls.columnconfigure(column, weight=1)

        self.ttk.Label(controls, text="Install Target", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 10)
        )
        self.ttk.Label(controls, text="AddOns path").grid(row=1, column=0, sticky="w")
        self.ttk.Entry(controls, textvariable=self.addons_path).grid(row=2, column=0, columnspan=3, sticky="ew", padx=(0, 8))
        self.ttk.Button(controls, text="Browse...", command=self._choose_addons_path).grid(row=2, column=3, sticky="ew")

        self.ttk.Label(controls, text="Region").grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.ttk.Label(controls, text="Locale").grid(row=3, column=1, sticky="w", pady=(12, 0))
        self.ttk.Label(controls, text="MM patch mode").grid(row=3, column=2, sticky="w", pady=(12, 0))

        self.ttk.Combobox(controls, textvariable=self.region, values=REGIONS, state="readonly").grid(
            row=4, column=0, sticky="ew", padx=(0, 8)
        )
        self.ttk.Combobox(controls, textvariable=self.locale, values=LOCALES, state="readonly").grid(
            row=4, column=1, sticky="ew", padx=(0, 8)
        )
        self.ttk.Combobox(
            controls,
            textvariable=self.patch_mode,
            values=list(PATCH_MODE_OPTIONS.keys()),
            state="readonly",
        ).grid(row=4, column=2, sticky="ew", padx=(0, 8))
        self.ttk.Checkbutton(controls, text="Dry run", variable=self.dry_run).grid(row=4, column=3, sticky="w")

        actions = self.ttk.Frame(controls, style="Card.TFrame")
        actions.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        for column in range(4):
            actions.columnconfigure(column, weight=1)

        self.status_button = self.ttk.Button(actions, text="Status", command=self._run_status, style="Run.TButton")
        self.validate_button = self.ttk.Button(actions, text="Validate", command=self._run_validate, style="Run.TButton")
        self.convert_button = self.ttk.Button(actions, text="Convert", command=self._run_convert, style="Run.TButton")
        self.clear_button = self.ttk.Button(actions, text="Clear log", command=self._clear_log)

        self.status_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.validate_button.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.convert_button.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        self.clear_button.grid(row=0, column=3, sticky="ew")

        output = self.ttk.Frame(outer, style="Card.TFrame", padding=14)
        output.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        output.columnconfigure(0, weight=1)
        output.rowconfigure(1, weight=1)

        self.ttk.Label(output, text="Activity", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.log = self.tk.Text(
            output,
            wrap="word",
            height=24,
            bg="#15241e",
            fg="#eef7f0",
            insertbackground="#eef7f0",
            padx=12,
            pady=12,
        )
        self.log.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        scrollbar = self.ttk.Scrollbar(output, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(10, 0))
        self.log.configure(yscrollcommand=scrollbar.set)

        footer = self.ttk.Frame(outer, style="App.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        self.ttk.Label(footer, textvariable=self.status_text, style="Subtitle.TLabel").grid(row=0, column=0, sticky="w")

    def _prefill_default_path(self) -> None:
        for candidate in _default_addons_candidates():
            if candidate.is_dir():
                self.addons_path.set(str(candidate))
                return

    def _choose_addons_path(self) -> None:
        chosen = self.filedialog.askdirectory(title="Choose ESO AddOns directory")
        if chosen:
            self.addons_path.set(chosen)

    def _clear_log(self) -> None:
        self.log.delete("1.0", self.tk.END)

    def _append_log(self, text: str) -> None:
        if not text:
            return
        self.log.insert(self.tk.END, text)
        if not text.endswith("\n"):
            self.log.insert(self.tk.END, "\n")
        self.log.see(self.tk.END)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        state = "disabled" if busy else "normal"
        self.status_button.configure(state=state)
        self.validate_button.configure(state=state)
        self.convert_button.configure(state=state)
        self.status_text.set(message or ("Working..." if busy else "Idle"))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "log" and payload is not None:
                self._append_log(payload)
            elif kind == "done":
                self._set_busy(False, payload or "Done")
            elif kind == "error":
                self._append_log(payload or "Unknown error")
                self._set_busy(False, "Failed")

        self.root.after(100, self._drain_events)

    def _emit(self, text: str) -> None:
        self.event_queue.put(("log", text))

    def _start_task(self, label: str, worker: threading.Thread) -> None:
        if self.worker is not None and self.worker.is_alive():
            self._append_log("A task is already running.")
            return
        self.worker = worker
        self._append_log(f"$ {label}")
        self._set_busy(True, label)
        self.worker.start()

    def _run_status(self) -> None:
        worker = threading.Thread(target=self._status_worker, daemon=True)
        self._start_task("status", worker)

    def _run_validate(self) -> None:
        worker = threading.Thread(target=self._validate_worker, daemon=True)
        self._start_task("validate", worker)

    def _run_convert(self) -> None:
        worker = threading.Thread(target=self._convert_worker, daemon=True)
        self._start_task("convert", worker)

    def _resolve_gui_paths(self):
        raw_path = self.addons_path.get().strip()
        if not raw_path:
            raise ValueError("AddOns path is required.")
        return resolve_paths(raw_path)

    def _capture_printed(self, callback, *args) -> tuple[str, object | None]:
        buffer = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(buffer):
            result = callback(*args)
        return buffer.getvalue(), result

    def _status_worker(self) -> None:
        try:
            paths = self._resolve_gui_paths()
            output, _ = self._capture_printed(run_status, paths)
            self._emit(output)
            self.event_queue.put(("done", "Status complete"))
        except Exception:
            self.event_queue.put(("error", traceback.format_exc()))

    def _validate_worker(self) -> None:
        try:
            paths = self._resolve_gui_paths()
            output, exit_code = self._capture_printed(run_validate, paths)
            self._emit(output)
            self._emit(f"Validation exit code: {exit_code}")
            self.event_queue.put(("done", "Validation complete"))
        except Exception:
            self.event_queue.put(("error", traceback.format_exc()))

    def _convert_worker(self) -> None:
        try:
            region = self.region.get().strip().upper()
            locale = self.locale.get().strip().upper()
            dry_run = self.dry_run.get()
            patch_mode = PATCH_MODE_OPTIONS[self.patch_mode.get()]
            paths = self._resolve_gui_paths()

            self._emit(f"  AddOns root : {paths.addons_root}")
            self._emit(
                "  Install mode: "
                + ("A (official TTC addon)" if paths.install_mode == "A" else "B (compat addon)")
            )
            if paths.saved_variables_dir:
                self._emit(f"  SavedVars   : {paths.saved_variables_dir}")
            else:
                self._emit("  SavedVars   : not found (MM patch step will be skipped)")
            self._emit("")

            self._emit(f"Downloading TTC price table ({region})...")
            if dry_run:
                extracted: dict[str, Path] = {}
                self._emit("  [dry-run] would download and extract files")
            else:
                extracted = download_price_table(region, locale=locale)
                for filename in extracted:
                    self._emit(f"  extracted: {filename}")
            self._emit("")

            self._emit("Installing TTC data...")
            if dry_run:
                self._emit("  [dry-run] would install files")
            else:
                if paths.install_mode == "A":
                    if paths.ttc_dir is None:
                        raise InstallerError("Official TTC install mode selected but addon folder is missing")
                    results = install_mode_a(paths.ttc_dir, extracted)
                else:
                    results = install_mode_b(paths.addons_root, extracted, region, locale)
                for filename, action in results:
                    self._emit(f"  {action}: {filename}")
            self._emit("")

            if patch_mode is None:
                self._emit("Skipping MM saved-variables patch (GUI set to 'No patch').")
                self.event_queue.put(("done", "Convert complete"))
                return

            if not paths.saved_variables_dir:
                self._emit("Skipping MM saved-variables patch (SavedVariables directory not found).")
                self.event_queue.put(("done", "Convert complete"))
                return

            saved_vars_path = find_saved_vars_file(paths.saved_variables_dir)
            if saved_vars_path is None:
                self._emit("Skipping MM saved-variables patch (Master Merchant saved vars file not found).")
                self.event_queue.put(("done", "Convert complete"))
                return

            self._emit(
                f"Patching {saved_vars_path.name} with {PRICE_MODE_LABELS[patch_mode]} settings..."
            )
            changes = build_ttc_patch_changes(patch_mode)
            backup, count = apply_patch_changes(saved_vars_path, changes, dry_run=dry_run)
            if dry_run:
                self._emit(f"  [dry-run] would apply {count} change(s).")
            else:
                if backup is not None:
                    self._emit(f"  Backed up to: {backup.name}")
                self._emit(f"  Applied {count} change(s).")

            self.event_queue.put(("done", "Convert complete"))
        except (DownloadError, ExtractError, InstallerError, PatcherError, PathResolverError, ValueError):
            self.event_queue.put(("error", f"error: {traceback.format_exc()}"))
        except Exception:
            self.event_queue.put(("error", traceback.format_exc()))


def main() -> None:
    parser = argparse.ArgumentParser(prog="ttc-mm-gui", add_help=True)
    parser.add_argument("--self-check", action="store_true", help="Print GUI/AppImage prerequisite status and exit.")
    args = parser.parse_args()

    if args.self_check:
        raise SystemExit(run_self_check())

    try:
        tk_mod, filedialog_mod, ttk_mod = _load_tk()
    except ImportError as exc:
        raise SystemExit(
            "tkinter is unavailable in this Python environment. Install Tk runtime libraries to use ttc-mm-gui."
        ) from exc

    root = tk_mod.Tk()
    app = TtcMmGui(root, tk_mod=tk_mod, filedialog_mod=filedialog_mod, ttk_mod=ttk_mod)
    app._append_log("ttc-mm GUI ready.")
    root.mainloop()


if __name__ == "__main__":
    main()