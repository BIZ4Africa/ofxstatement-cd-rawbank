#!/usr/bin/env python3
"""GUI application for OFX Statement Converter (Rawbank, D.R. Congo).

Provides a graphical front-end for the ofxstatement-cd-rawbank plugin,
allowing users to drag-and-drop or browse for source bank statement files,
select the bank, choose an output folder, and convert to OFX format.
"""

import os
import re
import site
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Namespace-package bootstrap
# When installed in editable/development mode (pip install -e .) the
# pkg_resources nspkg.pth may register *only* the project's src/ directory
# in ofxstatement.__path__, omitting the installed ofxstatement library
# (statement.py, ofx.py, …).  We patch the path here so that both the
# project plugin and the library sub-modules are always discoverable.
# ---------------------------------------------------------------------------
def _bootstrap_ofxstatement_namespace() -> None:
    import ofxstatement as _ofx

    installed_dirs = site.getsitepackages() + [site.getusersitepackages()]
    for sp in installed_dirs:
        candidate = os.path.join(sp, "ofxstatement")
        if os.path.isdir(candidate) and candidate not in list(_ofx.__path__):
            _ofx.__path__.append(candidate)


_bootstrap_ofxstatement_namespace()

APP_NAME = "OFX Statement Converter"
APP_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Bank registry
# Each entry maps a plugin identifier to its human-readable name, accent
# colour, and file-type filter used when browsing for source files.
# ---------------------------------------------------------------------------
BANK_REGISTRY = {
    "rawbankcd": {
        "display_name": "Rawbank\n(Congo, D.R.)",
        "short_name": "Rawbank – D.R. Congo",
        "color": "#003087",
        "text_color": "white",
        "file_types": [
            ("CSV Statement files", "*.csv"),
            ("All files", "*.*"),
        ],
    },
    "tmb": {
        "display_name": "TMB\n(Trust Merchant Bank)",
        "short_name": "Trust Merchant Bank",
        "color": "#C8102E",
        "text_color": "white",
        "file_types": [
            ("CSV Statement files", "*.csv"),
            ("All files", "*.*"),
        ],
        "coming_soon": True,
    },
    "equitybcdc": {
        "display_name": "Equity BCDC\n(Congo, D.R.)",
        "short_name": "Equity BCDC – D.R. Congo",
        "color": "#E31837",
        "text_color": "white",
        "file_types": [
            ("CSV Statement files", "*.csv"),
            ("All files", "*.*"),
        ],
        "coming_soon": True,
    },
}

# Maps each bank identifier to the dotted import path of its Plugin class.
# Extend this dict when adding support for additional banks.
_PLUGIN_CLASS_MAP: dict[str, str] = {
    "rawbankcd": "ofxstatement.plugins.rawbankcd.RawbankCdPlugin",
}

# Try to import tkinterdnd2 for native drag-and-drop support.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore

    _HAS_DND = True
except ImportError:
    _HAS_DND = False


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class DropZoneListbox(tk.Frame):
    """Combined drag-and-drop zone and multi-file list widget.

    Files can be added by clicking *Add*, by keyboard shortcut, or (when
    tkinterdnd2 is installed) by dragging files from the OS file manager.
    Multiple files are supported; the list can hold zero or more entries.
    """

    def __init__(self, parent, on_files_added=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_files_added = on_files_added
        self.files: list[str] = []
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        bg = self.cget("bg")

        # Toolbar row
        toolbar = tk.Frame(self, bg=bg)
        toolbar.pack(fill=tk.X, pady=(0, 4))

        ttk.Button(toolbar, text="➕ Add", width=7,
                   command=self.add_files).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(toolbar, text="✖ Remove", width=9,
                   command=self.remove_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🗑 Clear", width=8,
                   command=self.clear).pack(side=tk.LEFT, padx=2)

        # Listbox + scrollbar inside a sunken container
        list_container = tk.Frame(self, relief=tk.SUNKEN, borderwidth=2, bg=bg)
        list_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(
            list_container,
            selectmode=tk.EXTENDED,
            font=("TkDefaultFont", 9),
            activestyle="dotbox",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self.listbox.yview)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Hint shown when the list is empty
        self._hint = tk.Label(
            list_container,
            text="Drop files here\nor click ➕ Add",
            fg="#888888",
            bg="#ffffff",
            font=("TkDefaultFont", 10),
        )
        self._update_hint()

        # Register drag-and-drop target when tkinterdnd2 is available
        if _HAS_DND:
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)

    # ------------------------------------------------------------------
    def _update_hint(self) -> None:
        if not self.files:
            self._hint.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        else:
            self._hint.place_forget()

    def add_files(self) -> None:
        bank_id = getattr(self, "_current_bank", None)
        file_types: list = []
        if bank_id and bank_id in BANK_REGISTRY:
            file_types = BANK_REGISTRY[bank_id].get("file_types", [])
        file_types = file_types + [("All files", "*.*")]

        paths = filedialog.askopenfilenames(
            title="Select bank statement file(s)",
            filetypes=file_types,
        )
        if paths:
            self._add_file_list(list(paths))

    def _on_drop(self, event) -> None:
        paths = self.tk.splitlist(event.data)
        self._add_file_list(list(paths))

    def _add_file_list(self, paths: list[str]) -> None:
        added = []
        for path in paths:
            path = path.strip()
            if path and path not in self.files:
                self.files.append(path)
                self.listbox.insert(tk.END, os.path.basename(path))
                added.append(path)
        self._update_hint()
        if added and self.on_files_added:
            self.on_files_added(added)

    def remove_selected(self) -> None:
        selected = list(self.listbox.curselection())
        for idx in reversed(selected):
            self.files.pop(idx)
            self.listbox.delete(idx)
        self._update_hint()

    def clear(self) -> None:
        self.files.clear()
        self.listbox.delete(0, tk.END)
        self._update_hint()

    def get_files(self) -> list[str]:
        return list(self.files)

    def set_current_bank(self, bank_id: str) -> None:
        self._current_bank = bank_id


# ---------------------------------------------------------------------------


class BankSelectorPanel(tk.Frame):
    """Vertical panel of bank-selector buttons placed between source and
    destination panels."""

    def __init__(self, parent, on_bank_selected=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_bank_selected = on_bank_selected
        self.selected_bank: str | None = None
        self._buttons: dict[str, tk.Button] = {}
        self._build()

    def _build(self) -> None:
        bg = self.cget("bg")
        tk.Label(
            self,
            text="Select Bank",
            font=("TkDefaultFont", 9, "bold"),
            bg=bg,
        ).pack(pady=(4, 8))

        for bank_id, info in BANK_REGISTRY.items():
            frame = tk.Frame(self, bg=bg)
            frame.pack(pady=4, padx=4)

            coming_soon = info.get("coming_soon", False)

            btn = tk.Button(
                frame,
                text=info["display_name"],
                bg=info["color"] if not coming_soon else "#aaaaaa",
                fg=info["text_color"],
                font=("TkDefaultFont", 9, "bold" if not coming_soon else "normal"),
                width=14,
                height=3,
                relief=tk.RAISED,
                borderwidth=2,
                wraplength=110,
                state=tk.NORMAL if not coming_soon else tk.DISABLED,
                command=lambda bid=bank_id: self._select(bid),
            )
            btn.pack()

            if coming_soon:
                tk.Label(
                    frame,
                    text="Coming soon",
                    font=("TkDefaultFont", 7),
                    bg=bg,
                    fg="#888888",
                ).pack()

            self._buttons[bank_id] = btn

        # Auto-select the first available bank
        for bank_id, info in BANK_REGISTRY.items():
            if not info.get("coming_soon", False):
                self._select(bank_id)
                break

    def _select(self, bank_id: str) -> None:
        for bid, btn in self._buttons.items():
            btn.configure(relief=tk.RAISED, borderwidth=2)
        self.selected_bank = bank_id
        self._buttons[bank_id].configure(relief=tk.SUNKEN, borderwidth=4)
        if self.on_bank_selected:
            self.on_bank_selected(bank_id)

    def get_selected(self) -> str | None:
        return self.selected_bank


# ---------------------------------------------------------------------------


class DestinationPanel(tk.Frame):
    """Right panel: output folder browser and conversion log."""

    def __init__(self, parent, on_convert=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_convert = on_convert
        self._build()

    def _build(self) -> None:
        bg = self.cget("bg")

        # Output folder row
        folder_row = tk.Frame(self, bg=bg)
        folder_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(folder_row, text="Output folder:", bg=bg,
                 font=("TkDefaultFont", 9)).pack(side=tk.LEFT)
        self._dir_var = tk.StringVar(value=os.path.expanduser("~"))
        dir_entry = ttk.Entry(folder_row, textvariable=self._dir_var,
                              state="readonly", width=28)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(folder_row, text="Browse…",
                   command=self._browse).pack(side=tk.LEFT)

        # Log area
        tk.Label(self, text="Conversion log:", bg=bg,
                 font=("TkDefaultFont", 9)).pack(anchor=tk.W)
        log_container = tk.Frame(self, relief=tk.SUNKEN, borderwidth=2)
        log_container.pack(fill=tk.BOTH, expand=True)

        log_scroll = ttk.Scrollbar(log_container, orient=tk.VERTICAL)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(
            log_container,
            state=tk.DISABLED,
            font=("TkFixedFont", 9),
            bg="#f8f8f8",
            wrap=tk.WORD,
            yscrollcommand=log_scroll.set,
        )
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("success", foreground="#007700")
        self.log_text.tag_configure("info", foreground="#333333")
        log_scroll.configure(command=self.log_text.yview)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Convert button
        self.convert_btn = ttk.Button(
            self, text="▶  Convert to OFX", command=self._fire_convert
        )
        self.convert_btn.pack(pady=8)

    def _browse(self) -> None:
        directory = filedialog.askdirectory(
            title="Select output folder",
            initialdir=self._dir_var.get(),
        )
        if directory:
            self._dir_var.set(directory)

    def _fire_convert(self) -> None:
        if self._on_convert:
            self._on_convert()

    def get_output_dir(self) -> str:
        return self._dir_var.get()

    def log(self, message: str, tag: str = "info") -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n", tag)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def set_convert_enabled(self, enabled: bool) -> None:
        self.convert_btn.configure(
            state=tk.NORMAL if enabled else tk.DISABLED
        )


# ---------------------------------------------------------------------------


class AppInfoPanel(tk.Frame):
    """Far-right panel: application logo and version."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build()

    def _build(self) -> None:
        bg = self.cget("bg")

        # Logo / name block
        tk.Label(
            self,
            text="OFX\nConverter",
            font=("TkDefaultFont", 15, "bold"),
            bg=bg,
            fg="#003087",
            justify=tk.CENTER,
        ).pack(pady=(20, 4))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=6)

        tk.Label(
            self,
            text=f"v{APP_VERSION}",
            font=("TkDefaultFont", 10),
            bg=bg,
            fg="#555555",
        ).pack()

        tk.Label(
            self,
            text="ofxstatement\nplugin",
            font=("TkDefaultFont", 8),
            bg=bg,
            fg="#888888",
        ).pack(pady=(8, 0))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=12)

        tk.Label(
            self,
            text="© BIZ4Africa",
            font=("TkDefaultFont", 7),
            bg=bg,
            fg="#aaaaaa",
        ).pack()


# ---------------------------------------------------------------------------


class StatusBar(tk.Frame):
    """Bottom status bar: phase label on the left, statistics on the right."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, relief=tk.SUNKEN, borderwidth=1, **kwargs)
        self._build()

    def _build(self) -> None:
        # Phase label (left)
        self._phase_var = tk.StringVar(value="Ready")
        tk.Label(
            self,
            textvariable=self._phase_var,
            anchor=tk.W,
            padx=8,
            font=("TkDefaultFont", 9),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Separator(self, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, pady=2
        )

        # Statistics (right)
        stats = tk.Frame(self)
        stats.pack(side=tk.RIGHT, padx=8)

        tk.Label(stats, text="Transactions:", font=("TkDefaultFont", 9)).pack(
            side=tk.LEFT
        )
        self._txn_var = tk.StringVar(value="—")
        tk.Label(
            stats, textvariable=self._txn_var, font=("TkDefaultFont", 9, "bold"),
            width=5
        ).pack(side=tk.LEFT)

        ttk.Separator(stats, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, pady=2, padx=4
        )
        tk.Label(stats, text="Opening balance:", font=("TkDefaultFont", 9)).pack(
            side=tk.LEFT
        )
        self._open_var = tk.StringVar(value="—")
        tk.Label(
            stats, textvariable=self._open_var, font=("TkDefaultFont", 9, "bold"),
            width=12
        ).pack(side=tk.LEFT)

        ttk.Separator(stats, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, pady=2, padx=4
        )
        tk.Label(stats, text="Closing balance:", font=("TkDefaultFont", 9)).pack(
            side=tk.LEFT
        )
        self._close_var = tk.StringVar(value="—")
        tk.Label(
            stats, textvariable=self._close_var, font=("TkDefaultFont", 9, "bold"),
            width=12
        ).pack(side=tk.LEFT)

    # Public helpers
    def set_phase(self, text: str) -> None:
        self._phase_var.set(text)
        self.update_idletasks()

    def set_stats(
        self,
        transactions: int | None = None,
        opening: float | None = None,
        closing: float | None = None,
    ) -> None:
        if transactions is not None:
            self._txn_var.set(str(transactions))
        if opening is not None:
            self._open_var.set(f"{opening:,.2f}")
        if closing is not None:
            self._close_var.set(f"{closing:,.2f}")

    def reset(self) -> None:
        self._phase_var.set("Ready")
        self._txn_var.set("—")
        self._open_var.set("—")
        self._close_var.set("—")


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class OFXConverterApp:
    """Main application window."""

    BG = "#f0f0f0"

    def __init__(self) -> None:
        if _HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title(f"{APP_NAME}  —  v{APP_VERSION}")
        self.root.geometry("1200x660")
        self.root.minsize(900, 520)
        self.root.configure(bg=self.BG)

        self._selected_bank: str | None = None

        self._build_menu()
        self._build_ui()
        self._bind_shortcuts()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        # --- File ---
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(
            label="Add Files…",
            accelerator="Ctrl+O",
            command=lambda: self.source_panel.add_files(),
        )
        file_menu.add_command(
            label="Remove Selected",
            command=lambda: self.source_panel.remove_selected(),
        )
        file_menu.add_command(
            label="Clear All Files",
            command=lambda: self.source_panel.clear(),
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Convert to OFX",
            accelerator="Ctrl+Return",
            command=self._convert,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Exit",
            accelerator="Ctrl+Q",
            command=self.root.quit,
        )
        menubar.add_cascade(label="File", menu=file_menu)

        # --- Edit ---
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(
            label="Select All Source Files",
            command=lambda: self.source_panel.listbox.select_set(0, tk.END),
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Clear Conversion Log",
            command=lambda: self.dest_panel.clear_log(),
        )
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # --- Help ---
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About…", command=self._show_about)
        help_menu.add_command(
            label="Project on GitHub",
            command=lambda: messagebox.showinfo(
                "Project URL",
                "https://github.com/BIZ4Africa/ofxstatement-cd-rawbank",
            ),
        )
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=menubar)

    # ------------------------------------------------------------------
    # Main layout
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        bg = self.BG

        # ---- Content area (everything above the status bar) ----
        content = tk.Frame(self.root, bg=bg)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Left panel – source files
        left_frame = tk.LabelFrame(
            content,
            text=" Source Files ",
            bg=bg,
            font=("TkDefaultFont", 10, "bold"),
            padx=6,
            pady=6,
        )
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        self.source_panel = DropZoneListbox(
            left_frame,
            bg=bg,
            on_files_added=self._on_files_added,
        )
        self.source_panel.pack(fill=tk.BOTH, expand=True)

        # Centre panel – bank selection
        centre_frame = tk.LabelFrame(
            content,
            text=" Bank ",
            bg=bg,
            font=("TkDefaultFont", 10, "bold"),
            padx=4,
            pady=4,
        )
        centre_frame.pack(side=tk.LEFT, fill=tk.Y, padx=4)

        self.bank_panel = BankSelectorPanel(
            centre_frame,
            bg=bg,
            on_bank_selected=self._on_bank_selected,
        )
        self.bank_panel.pack(fill=tk.BOTH, expand=True)

        # Right panel – destination
        right_frame = tk.LabelFrame(
            content,
            text=" Destination ",
            bg=bg,
            font=("TkDefaultFont", 10, "bold"),
            padx=6,
            pady=6,
        )
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 4))

        self.dest_panel = DestinationPanel(
            right_frame,
            bg=bg,
            on_convert=self._convert,
        )
        self.dest_panel.pack(fill=tk.BOTH, expand=True)

        # Far-right panel – app info
        info_frame = tk.LabelFrame(
            content,
            text="",
            bg=bg,
            padx=4,
            pady=4,
            width=130,
        )
        info_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 0))
        info_frame.pack_propagate(False)

        AppInfoPanel(info_frame, bg=bg).pack(fill=tk.BOTH, expand=True)

        # ---- Status bar ----
        self.status_bar = StatusBar(self.root, bg=bg)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _e: self.source_panel.add_files())
        self.root.bind("<Control-q>", lambda _e: self.root.quit())
        self.root.bind("<Control-Return>", lambda _e: self._convert())

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_files_added(self, paths: list[str]) -> None:
        n = len(paths)
        self.status_bar.set_phase(
            f"Added {n} file{'s' if n != 1 else ''}. "
            f"Total: {len(self.source_panel.get_files())} file(s) queued."
        )

    def _on_bank_selected(self, bank_id: str) -> None:
        self._selected_bank = bank_id
        if hasattr(self, "source_panel"):
            self.source_panel.set_current_bank(bank_id)
        if hasattr(self, "status_bar"):
            name = BANK_REGISTRY[bank_id]["short_name"]
            self.status_bar.set_phase(f"Bank selected: {name}")

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _convert(self) -> None:
        files = self.source_panel.get_files()
        if not files:
            messagebox.showwarning(
                "No Source Files",
                "Please add at least one source file before converting.",
            )
            return

        bank_id = self.bank_panel.get_selected()
        if not bank_id:
            messagebox.showwarning("No Bank Selected", "Please select a bank.")
            return

        if BANK_REGISTRY.get(bank_id, {}).get("coming_soon"):
            messagebox.showinfo(
                "Coming Soon",
                f"Support for {BANK_REGISTRY[bank_id]['short_name']} "
                "is not yet available.",
            )
            return

        output_dir = self.dest_panel.get_output_dir()
        if not os.path.isdir(output_dir):
            messagebox.showerror(
                "Invalid Output Folder",
                f"The folder '{output_dir}' does not exist.\n"
                "Please choose a valid output folder.",
            )
            return

        self.dest_panel.clear_log()
        self.status_bar.reset()
        self.dest_panel.set_convert_enabled(False)

        threading.Thread(
            target=self._run_conversion,
            args=(files, bank_id, output_dir),
            daemon=True,
        ).start()

    def _run_conversion(
        self, files: list[str], bank_id: str, output_dir: str
    ) -> None:
        total_txns = 0
        first_opening: float | None = None
        last_closing: float | None = None
        errors = 0

        for i, filepath in enumerate(files, start=1):
            fname = os.path.basename(filepath)
            self._ui(
                self.status_bar.set_phase,
                f"Converting {fname}  ({i}/{len(files)})…",
            )
            self._ui(
                self.dest_panel.log,
                f"▶ Processing: {filepath}",
                "info",
            )

            try:
                output_path = self._convert_one(filepath, bank_id, output_dir)
                txns, opening, closing = self._extract_stats(output_path)
                total_txns += txns
                if first_opening is None and opening is not None:
                    first_opening = opening
                if closing is not None:
                    last_closing = closing

                self._ui(
                    self.dest_panel.log,
                    f"  ✔ Saved: {output_path}  ({txns} transaction(s))",
                    "success",
                )
                self._ui(
                    self.status_bar.set_stats,
                    total_txns,
                    first_opening,
                    last_closing,
                )
            except Exception as exc:
                errors += 1
                self._ui(
                    self.dest_panel.log,
                    f"  ✘ Error: {exc}",
                    "error",
                )

        self._ui(
            self.dest_panel.log,
            "─" * 50,
            "info",
        )
        summary = (
            f"Done. {total_txns} transaction(s) converted from "
            f"{len(files)} file(s)"
            + (f" ({errors} error(s))" if errors else "")
            + "."
        )
        self._ui(self.dest_panel.log, summary, "success" if not errors else "error")
        self._ui(
            self.status_bar.set_phase,
            f"Conversion complete — {summary}",
        )
        self._ui(self.dest_panel.set_convert_enabled, True)

    def _convert_one(
        self, filepath: str, bank_id: str, output_dir: str
    ) -> str:
        """Convert *filepath* using the plugin registered for *bank_id*."""
        import importlib
        from ofxstatement.ofx import OfxWriter

        plugin_path = _PLUGIN_CLASS_MAP.get(bank_id)
        if not plugin_path:
            raise ValueError(f"No plugin registered for bank '{bank_id}'.")

        module_name, class_name = plugin_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        plugin_cls = getattr(module, class_name)

        stem = os.path.splitext(os.path.basename(filepath))[0]
        output_path = os.path.join(output_dir, f"{stem}.ofx")

        plugin = plugin_cls(None, {})
        parser = plugin.get_parser(filepath)
        stmt = parser.parse()

        with open(output_path, "w", encoding="utf-8") as fout:
            fout.write(OfxWriter(stmt).toxml(pretty=True))

        return output_path

    @staticmethod
    def _extract_stats(
        ofx_path: str,
    ) -> tuple[int, float | None, float | None]:
        """Parse transaction count and balances from the generated OFX file."""
        try:
            with open(ofx_path, "r", encoding="utf-8") as f:
                content = f.read()

            txns = len(re.findall(r"<STMTTRN>", content, re.IGNORECASE))
            balances = re.findall(r"<BALAMT>([-\d.]+)", content, re.IGNORECASE)
            opening = float(balances[0]) if balances else None
            closing = float(balances[-1]) if balances else None
            return txns, opening, closing
        except Exception:
            return 0, None, None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ui(self, func, *args) -> None:
        """Schedule *func(*args)* on the main thread."""
        self.root.after(0, lambda: func(*args))

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About",
            f"{APP_NAME}\n"
            f"Version: {APP_VERSION}\n\n"
            "Converts Rawbank (D.R. Congo) bank statements\n"
            "from CSV format to OFX, for use with\n"
            "GnuCash, Odoo, and other accounting tools.\n\n"
            "© BIZ4Africa\n"
            "https://github.com/BIZ4Africa/ofxstatement-cd-rawbank",
        )

    # ------------------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


# ---------------------------------------------------------------------------


def main() -> None:
    app = OFXConverterApp()
    app.run()


if __name__ == "__main__":
    main()
