"""
Skills Manager - GUI Application (tkinter)
v3 — Optimized: debounced search, manifest snapshot, hover effects,
     dynamic wraplength, cross-platform scroll, category filter,
     enhanced Sources tab, relevance-filtered Discover.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import webbrowser
import platform
from skill_core import (
    fetch_registry,
    is_installed,
    get_installed_version,
    get_installed_snapshot,
    has_update,
    install_skill,
    uninstall_skill,
    search_skills,
    get_all_categories,
    get_registry_sources,
    discover_github_repos,
    get_cached_discoveries,
    add_source_to_registry,
    remove_source_from_registry,
    fetch_skills_from_github_repo,
    merge_discovered_skills,
    ensure_dirs,
    scan_single_skill,
    scan_remote_skill,
    scan_all_installed,
    get_scan_results,
    get_skill_scan,
    get_proxy_config,
    set_proxy_config,
)
import db as skilldb

# ── Color Palette (Catppuccin Mocha) ───────────────────────────
BG = "#1e1e2e"
BG_CARD = "#2a2a3d"
BG_HOVER = "#33334d"
FG = "#cdd6f4"
FG_DIM = "#7f849c"
ACCENT = "#89b4fa"
GREEN = "#a6e3a1"
RED = "#f38ba8"
YELLOW = "#f9e2af"
ORANGE = "#fab387"
BORDER = "#45475a"
SEARCH_BG = "#313244"
IS_MAC = platform.system() == "Darwin"


# ── Hover mixin ────────────────────────────────────────────────

class ToastNotification:
    """Toast notification with optional action button."""
    def __init__(self, parent, message: str, action_text: str = None, 
                 action_callback=None, duration: int = 5000):
        self.toast = tk.Toplevel(parent)
        self.toast.overrideredirect(True)
        self.toast.configure(bg=BG_CARD)
        
        # Position: bottom right
        parent.update_idletasks()
        x = parent.winfo_x() + parent.winfo_width() - 320
        y = parent.winfo_y() + parent.winfo_height() - 100
        self.toast.geometry(f"300x60+{x}+{y}")
        
        frame = tk.Frame(self.toast, bg=BG_CARD, highlightbackground=GREEN,
                        highlightthickness=2)
        frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        tk.Label(frame, text=message, font=("Helvetica", 11),
                fg=FG, bg=BG_CARD).pack(side="left", padx=12, pady=12)
        
        if action_text and action_callback:
            tk.Button(frame, text=action_text, font=("Helvetica", 10, "bold"),
                     fg=ACCENT, bg=BG_CARD, relief="flat", cursor="hand2",
                     command=lambda: [action_callback(), self.close()]
                     ).pack(side="right", padx=8)
        
        tk.Button(frame, text="×", font=("Helvetica", 14),
                 fg=FG_DIM, bg=BG_CARD, relief="flat", cursor="hand2",
                 command=self.close).pack(side="right", padx=4)
        
        self.toast.after(duration, self.close)
    
    def close(self):
        try:
            self.toast.destroy()
        except:
            pass


class ScanTracker(tk.Toplevel):
    """Non-modal scan progress dialog with scrollable result log. User closes manually."""

    def __init__(self, parent, title="Scan Progress"):
        super().__init__(parent)
        self.title(title)
        self.geometry("560x380")
        self.configure(bg=BG)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._done = False
        self._on_finish_cb = None

        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        self._title_var = tk.StringVar(value="Starting...")
        tk.Label(hdr, textvariable=self._title_var,
                 font=("Helvetica", 13, "bold"), fg=FG, bg=BG).pack(side="left")
        self._stats_var = tk.StringVar()
        tk.Label(hdr, textvariable=self._stats_var,
                 font=("Helvetica", 10), fg=FG_DIM, bg=BG).pack(side="right")

        self._pv = tk.DoubleVar()
        ttk.Progressbar(self, variable=self._pv, maximum=100,
                        length=520).pack(padx=16, pady=(0, 8))

        log_frame = tk.Frame(self, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._log = tk.Text(log_frame, bg=SEARCH_BG, fg=FG, font=("Consolas", 10),
                            relief="flat", wrap="word", state="disabled",
                            highlightthickness=1, highlightbackground=BORDER)
        sb = ttk.Scrollbar(log_frame, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        self._log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._log.tag_configure("ok", foreground=GREEN)
        self._log.tag_configure("high", foreground=RED)
        self._log.tag_configure("med", foreground=YELLOW)
        self._log.tag_configure("low", foreground=ACCENT)
        self._log.tag_configure("fail", foreground=RED)
        self._log.tag_configure("info", foreground=FG_DIM)

        self._close_btn = tk.Button(
            self, text="Close", font=("Helvetica", 11, "bold"),
            fg=FG, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=20, pady=6,
            state="disabled", command=self._on_close)
        self._close_btn.pack(pady=(0, 12))

    def log(self, text: str, tag: str = ""):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n", tag or ())
        self._log.see("end")
        self._log.configure(state="disabled")

    def set_progress(self, current: int, total: int, name: str = ""):
        pct = (current / total * 100) if total else 100
        self._pv.set(pct)
        self._title_var.set(f"Scanning {current}/{total}...")
        if name:
            self._stats_var.set(name)

    def finish(self, summary: str):
        self._done = True
        self._title_var.set("✓ Scan Complete")
        self._stats_var.set(summary)
        self._pv.set(100)
        self._close_btn.configure(state="normal")

    def on_finish(self, cb):
        self._on_finish_cb = cb
        # If already done, fire immediately
        if self._done:
            cb()

    def _on_close(self):
        if self._done:
            if self._on_finish_cb:
                self._on_finish_cb()
            self.destroy()


class ToolTip:
    """Hover tooltip for any widget."""
    def __init__(self, widget, text: str):
        self._w = widget
        self._text = text
        self._tw = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, e=None):
        x = self._w.winfo_rootx() + self._w.winfo_width() // 2
        y = self._w.winfo_rooty() + self._w.winfo_height() + 4
        self._tw = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self._text, font=("Helvetica", 9), fg=FG,
                 bg=BG_CARD, relief="solid", bd=1, padx=6, pady=2).pack()

    def _hide(self, e=None):
        if self._tw:
            self._tw.destroy()
            self._tw = None


def _bind_hover(widget: tk.Frame, normal_bg: str = BG_CARD, hover_bg: str = BG_HOVER):
    """Recursively bind hover color change to a frame and all children."""
    def _enter(e):
        widget.configure(bg=hover_bg)
        _set_children_bg(widget, hover_bg)

    def _leave(e):
        widget.configure(bg=normal_bg)
        _set_children_bg(widget, normal_bg)

    widget.bind("<Enter>", _enter)
    widget.bind("<Leave>", _leave)


def _set_children_bg(parent, bg):
    """Set bg on all child widgets that support it (Label, Frame)."""
    for child in parent.winfo_children():
        try:
            wtype = child.winfo_class()
            # Don't change Button bg (they have their own colors)
            if wtype in ("Label", "Frame"):
                child.configure(bg=bg)
                _set_children_bg(child, bg)
        except tk.TclError:
            pass


# ── SkillCard ──────────────────────────────────────────────────

class SkillCard(tk.Frame):
    """A single skill card with hover effect and batch-select checkbox."""

    def __init__(self, parent, skill: dict, on_action, snapshot: dict,
                 check_var: tk.BooleanVar | None = None,
                 scan_result: dict | None = None, **kw):
        super().__init__(parent, bg=BG_CARD, highlightbackground=BORDER,
                         highlightthickness=1, **kw)
        self.skill = skill
        self.on_action = on_action
        self._snapshot = snapshot
        self._check_var = check_var
        self._scan_result = scan_result
        self._desc_label: tk.Label | None = None
        self._info_label: tk.Label | None = None
        self._build()
        _bind_hover(self)
        if self._check_var is not None:
            self._bind_double_click(self)

    def _toggle_check(self, e=None):
        self._check_var.set(not self._check_var.get())
        self.on_action("_selection_changed", None)

    def _bind_double_click(self, widget):
        widget.bind("<Double-Button-1>", self._toggle_check)
        for child in widget.winfo_children():
            if child.winfo_class() not in ("Button", "Checkbutton"):
                self._bind_double_click(child)

    def _build(self):
        s = self.skill
        snap = self._snapshot
        inst = is_installed(s["id"], snap)
        upd = has_update(s, snap)
        sr = self._scan_result

        # Status left border — scan severity overrides install color
        if sr and sr.get("severity") == "HIGH":
            border_color = RED
        elif sr and sr.get("severity") == "MEDIUM":
            border_color = YELLOW
        elif inst and upd:
            border_color = YELLOW
        elif inst:
            border_color = GREEN
        else:
            border_color = BORDER
        
        left_border = tk.Frame(self, bg=border_color, width=4)
        left_border.pack(side="left", fill="y")
        
        # Main content container
        content = tk.Frame(self, bg=BG_CARD)
        content.pack(side="left", fill="both", expand=True)

        # Row 1: checkbox + name + version + category
        top = tk.Frame(content, bg=BG_CARD)
        top.pack(fill="x", padx=12, pady=(10, 2))

        if self._check_var is not None:
            cb = tk.Checkbutton(
                top, variable=self._check_var,
                bg=BG_CARD, activebackground=BG_HOVER,
                selectcolor=SEARCH_BG, relief="flat", bd=0,
                command=lambda: self.on_action("_selection_changed", None),
            )
            cb.pack(side="left", padx=(0, 6))

        tk.Label(top, text=s["name"], font=("Helvetica", 14, "bold"),
                 fg=FG, bg=BG_CARD, anchor="w").pack(side="left")
        tk.Label(top, text=f'v{s["version"]}', font=("Helvetica", 10),
                 fg=FG_DIM, bg=BG_CARD).pack(side="left", padx=(8, 0))
        tk.Label(top, text=s.get("category", ""), font=("Helvetica", 9),
                 fg=ACCENT, bg=BG_CARD).pack(side="right")

        # Row 2: author · repo · size
        meta = tk.Frame(content, bg=BG_CARD)
        meta.pack(fill="x", padx=12, pady=(0, 4))
        author = f'by {s.get("author", "unknown")}'
        if s.get("repo"):
            author += f'  ·  {s["repo"]}'
        tk.Label(meta, text=author, font=("Helvetica", 9),
                 fg=FG_DIM, bg=BG_CARD).pack(side="left")
        tk.Label(meta, text=s.get("size", ""), font=("Helvetica", 9),
                 fg=FG_DIM, bg=BG_CARD).pack(side="right")

        # Row 3: description (dynamic wraplength)
        self._desc_label = tk.Label(
            content, text=s.get("description", ""), font=("Helvetica", 11),
            fg=FG, bg=BG_CARD, anchor="w", justify="left", wraplength=500,
        )
        self._desc_label.pack(fill="x", padx=12, pady=(0, 4))

        # Row 4: tags
        if s.get("tags"):
            tf = tk.Frame(content, bg=BG_CARD)
            tf.pack(fill="x", padx=12, pady=(0, 4))
            for tag in s["tags"][:6]:
                tk.Label(tf, text=f" {tag} ", font=("Helvetica", 9),
                         fg=ACCENT, bg=SEARCH_BG, padx=4, pady=1,
                         relief="flat").pack(side="left", padx=(0, 4))

        # Row 5: scan result (if installed)
        if inst or sr:
            scan_row = tk.Frame(content, bg=BG_CARD)
            scan_row.pack(fill="x", padx=12, pady=(0, 4))
            if sr:
                sev = sr.get("severity", "NONE")
                fc = sr.get("findings_count", 0)
                sev_colors = {"HIGH": RED, "MEDIUM": YELLOW, "LOW": ACCENT, "NONE": GREEN}
                sev_icons = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵", "NONE": "🟢"}
                sc = sev_colors.get(sev, FG_DIM)
                icon = sev_icons.get(sev, "")
                ts = sr.get("timestamp", "")
                if fc == 0:
                    scan_text = f"{icon} Clean — no issues found"
                else:
                    cats = ", ".join(sr.get("categories", []))
                    scan_text = f"{icon} {sev}: {fc} finding{'s' if fc != 1 else ''} ({cats})"
                lbl = tk.Label(scan_row, text=scan_text, font=("Helvetica", 9),
                               fg=sc, bg=BG_CARD)
                lbl.pack(side="left")
                # Click to view details if there are findings
                if fc > 0:
                    lbl.configure(cursor="hand2")
                    lbl.bind("<Button-1>",
                             lambda e, sid=s["id"]: self.on_action("scan_details", s))
                if ts:
                    tk.Label(scan_row, text=ts, font=("Helvetica", 8),
                             fg=FG_DIM, bg=BG_CARD).pack(side="right")
            else:
                tk.Label(scan_row, text="⚪ Not scanned", font=("Helvetica", 9),
                         fg=FG_DIM, bg=BG_CARD).pack(side="left")

        # Row 6: status + buttons
        bot = tk.Frame(content, bg=BG_CARD)
        bot.pack(fill="x", padx=12, pady=(2, 10))

        if inst and not upd:
            tk.Label(bot, text="✓ Installed", font=("Helvetica", 10, "bold"),
                     fg=GREEN, bg=BG_CARD).pack(side="left")
            v = get_installed_version(s["id"], snap)
            if v:
                tk.Label(bot, text=f"(v{v})", font=("Helvetica", 9),
                         fg=FG_DIM, bg=BG_CARD).pack(side="left", padx=(4, 0))
            self._btn(bot, "Uninstall", RED, BG_CARD, "uninstall",
                      "Remove this skill from local storage").pack(side="right")
            self._btn(bot, "🛡 Security Scan", FG, SEARCH_BG, "scan",
                      "Scan local files for malicious patterns").pack(side="right", padx=(0, 8))

        elif inst and upd:
            tk.Label(bot, text="⬆ Update available", font=("Helvetica", 10, "bold"),
                     fg=YELLOW, bg=BG_CARD).pack(side="left")
            self._btn(bot, "Update", BG, YELLOW, "install",
                      "Download and install the latest version").pack(side="right")
            self._btn(bot, "Uninstall", RED, BG_CARD, "uninstall",
                      "Remove this skill from local storage").pack(side="right", padx=(0, 8))
            self._btn(bot, "🛡 Security Scan", FG, SEARCH_BG, "scan",
                      "Scan local files for malicious patterns").pack(side="right", padx=(0, 8))

        else:
            self._btn(bot, "Install", BG, ACCENT, "install",
                      "Download and install this skill").pack(side="right")
            if s.get("repo") or s.get("url"):
                self._btn(bot, "🛡 Pre-scan", FG, SEARCH_BG, "scan",
                          "Download to temp, scan for threats, then discard"
                          ).pack(side="right", padx=(0, 8))

        if s.get("url"):
            _gb = tk.Button(
                bot, text="🔗 GitHub", font=("Helvetica", 9),
                fg=FG_DIM, bg=BG_CARD, activeforeground=FG, activebackground=BG_HOVER,
                relief="flat", cursor="hand2", bd=0,
                command=lambda: webbrowser.open(s["url"]),
            )
            _gb.pack(side="right", padx=(0, 8))
            ToolTip(_gb, f"Open {s['url']} in browser")

    def _btn(self, parent, text, fg_c, bg_c, action, tip=""):
        b = tk.Button(
            parent, text=text, font=("Helvetica", 10, "bold"),
            fg=fg_c, bg=bg_c, activeforeground=fg_c,
            activebackground=BG_HOVER, relief="flat", cursor="hand2",
            bd=0, padx=14, pady=4,
            command=lambda: self.on_action(action, self.skill),
        )
        if tip:
            ToolTip(b, tip)
        return b

    def update_wraplength(self, width: int):
        if self._desc_label:
            self._desc_label.configure(wraplength=max(200, width - 50))


# ── RepoCard ───────────────────────────────────────────────────

class RepoCard(tk.Frame):
    def __init__(self, parent, repo: dict, on_action, **kw):
        super().__init__(parent, bg=BG_CARD, highlightbackground=BORDER,
                         highlightthickness=1, **kw)
        self.repo = repo
        self.on_action = on_action
        self._desc_label = None
        self._build()
        _bind_hover(self)

    def _build(self):
        r = self.repo
        top = tk.Frame(self, bg=BG_CARD)
        top.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(top, text=r.get("name", ""), font=("Helvetica", 14, "bold"),
                 fg=FG, bg=BG_CARD, anchor="w").pack(side="left")
        tk.Label(top, text=f'⭐ {r.get("stars", 0)}', font=("Helvetica", 10),
                 fg=YELLOW, bg=BG_CARD).pack(side="right")
        if r.get("language"):
            tk.Label(top, text=r["language"], font=("Helvetica", 9),
                     fg=ORANGE, bg=BG_CARD).pack(side="right", padx=(0, 10))

        # Relevance badge
        rel = r.get("_relevance", 0)
        if rel >= 40:
            tk.Label(top, text="● highly relevant", font=("Helvetica", 8),
                     fg=GREEN, bg=BG_CARD).pack(side="right", padx=(0, 10))
        elif rel >= 20:
            tk.Label(top, text="● relevant", font=("Helvetica", 8),
                     fg=YELLOW, bg=BG_CARD).pack(side="right", padx=(0, 10))

        meta = tk.Frame(self, bg=BG_CARD)
        meta.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(meta, text=r.get("repo", ""), font=("Helvetica", 10),
                 fg=ACCENT, bg=BG_CARD).pack(side="left")

        desc = r.get("description", "")
        if desc:
            self._desc_label = tk.Label(
                self, text=desc, font=("Helvetica", 11),
                fg=FG, bg=BG_CARD, anchor="w", wraplength=500, justify="left",
            )
            self._desc_label.pack(fill="x", padx=12, pady=(0, 4))

        bot = tk.Frame(self, bg=BG_CARD)
        bot.pack(fill="x", padx=12, pady=(2, 10))
        tk.Button(
            bot, text="➕ Add & Scan", font=("Helvetica", 10, "bold"),
            fg=BG, bg=GREEN, activeforeground=BG, activebackground="#8bc98a",
            relief="flat", cursor="hand2", bd=0, padx=14, pady=4,
            command=lambda: self.on_action("add_source", self.repo),
        ).pack(side="right")
        tk.Button(
            bot, text="🔗 Open", font=("Helvetica", 9),
            fg=FG_DIM, bg=BG_CARD, activeforeground=FG, activebackground=BG_HOVER,
            relief="flat", cursor="hand2", bd=0,
            command=lambda: webbrowser.open(r.get("url", "")),
        ).pack(side="right", padx=(0, 8))

    def update_wraplength(self, width: int):
        if self._desc_label:
            self._desc_label.configure(wraplength=max(200, width - 50))


# ── SourceCard (enhanced: rescan + remove) ─────────────────────

class SourceCard(tk.Frame):
    def __init__(self, parent, source: dict, on_action=None, **kw):
        super().__init__(parent, bg=BG_CARD, highlightbackground=BORDER,
                         highlightthickness=1, **kw)
        self.source = source
        self.on_action = on_action
        self._build()
        _bind_hover(self)

    def _build(self):
        s = self.source
        row = tk.Frame(self, bg=BG_CARD)
        row.pack(fill="x", padx=12, pady=8)

        tk.Label(row, text=s.get("name", ""), font=("Helvetica", 12, "bold"),
                 fg=FG, bg=BG_CARD).pack(side="left")
        tk.Label(row, text=s.get("repo", ""), font=("Helvetica", 10),
                 fg=FG_DIM, bg=BG_CARD).pack(side="left", padx=(10, 0))

        if self.on_action:
            tk.Button(
                row, text="🗑", font=("Helvetica", 10),
                fg=RED, bg=BG_CARD, activeforeground=RED, activebackground=BG_HOVER,
                relief="flat", cursor="hand2", bd=0,
                command=lambda: self.on_action("remove", self.source),
            ).pack(side="right", padx=(4, 0))
            tk.Button(
                row, text="🔄 Rescan", font=("Helvetica", 9),
                fg=ACCENT, bg=BG_CARD, activeforeground=FG, activebackground=BG_HOVER,
                relief="flat", cursor="hand2", bd=0,
                command=lambda: self.on_action("rescan", self.source),
            ).pack(side="right", padx=(4, 0))

        tk.Button(
            row, text="🔗", font=("Helvetica", 9),
            fg=FG_DIM, bg=BG_CARD, activeforeground=FG, activebackground=BG_HOVER,
            relief="flat", cursor="hand2", bd=0,
            command=lambda: webbrowser.open(s.get("url", "")),
        ).pack(side="right")


# ── Main Application ───────────────────────────────────────────

class SkillsManagerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("⚡ Skills Manager")
        self.root.configure(bg=BG)
        self.root.minsize(640, 550)
        self._set_icon()

        # Adaptive window size based on screen
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = min(max(int(sw * 0.5), 780), 1200)
        h = min(max(int(sh * 0.7), 760), 1000)
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.all_skills: list[dict] = []
        self.discovered_repos: list[dict] = []
        self.current_filter = "all"
        self.current_category = ""  # "" = all categories
        self.current_sort = "name"  # name | risk | category
        self._debounce_id = None
        self._cards: list = []  # track rendered cards for wraplength updates
        self._content_width = 700
        self._info_label: tk.Label | None = None
        # Pagination state
        self._page = 0
        self._page_size = 30
        self._total_skills = 0
        # Batch selection: skill_id -> BooleanVar
        self._check_vars: dict[str, tk.BooleanVar] = {}
        self._batch_bar: tk.Frame | None = None

        ensure_dirs()
        # Migrate JSON data to SQLite on first run
        if not skilldb.DB_PATH.exists():
            skilldb.migrate_from_json()
        self._build_ui()
        self._setup_keyboard_shortcuts()
        self._refresh_registry()

    # ── UI Build ───────────────────────────────────────────────

    def _set_icon(self):
        """Generate and set a custom window icon (lightning bolt on blue bg)."""
        try:
            sz = 64
            bolt = [(28,4),(18,30),(29,30),(20,60),(46,24),(33,24),(40,4)]

            def _in_bolt(px, py):
                inside = False
                j = len(bolt) - 1
                for i in range(len(bolt)):
                    xi, yi = bolt[i]; xj, yj = bolt[j]
                    if ((yi > py) != (yj > py)) and \
                       (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                        inside = not inside
                    j = i
                return inside

            data = bytearray()
            for y in range(sz):
                for x in range(sz):
                    r2 = 12
                    cx, cy = min(max(x, r2), sz-1-r2), min(max(y, r2), sz-1-r2)
                    if (x-cx)**2 + (y-cy)**2 > r2*r2:
                        data += b'\x1e\x1e\x1e'
                    elif _in_bolt(x, y):
                        t = y / sz
                        data += bytes((255, min(int(220+35*(1-t)), 255), 60))
                    else:
                        t = y / sz
                        data += bytes((int(50+30*t), int(100+50*t), int(200-20*t)))

            img = tk.PhotoImage(data=f"P6\n{sz} {sz}\n255\n".encode() + bytes(data),
                                format="ppm")
            self.root.iconphoto(True, img)
            self._icon_img = img  # prevent GC
        except Exception:
            pass

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(hdr, text="⚡ Skills Manager", font=("Helvetica", 20, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left")
        _rb = tk.Button(
            hdr, text="↻ Refresh", font=("Helvetica", 11),
            fg=ACCENT, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=10, pady=4,
            command=self._refresh_registry,
        )
        _rb.pack(side="right")
        ToolTip(_rb, "Re-fetch skill registry from remote sources (Ctrl+R)")
        proxy_icon = "🌐" if get_proxy_config().get("enabled") else "⚙"
        self._proxy_btn = tk.Button(
            hdr, text=f"{proxy_icon} Proxy", font=("Helvetica", 11),
            fg=FG_DIM, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=10, pady=4,
            command=self._show_proxy_settings,
        )
        self._proxy_btn.pack(side="right", padx=(0, 8))
        ToolTip(self._proxy_btn, "Configure HTTP/HTTPS proxy for network access")
        _sb = tk.Button(
            hdr, text="🛡 Scan All Installed", font=("Helvetica", 11),
            fg=ORANGE, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=10, pady=4,
            command=self._do_scan_all,
        )
        _sb.pack(side="right", padx=(0, 8))
        ToolTip(_sb, "Security scan all installed skills for malicious patterns")

        # Search bar (proper placeholder via focus + color swap)
        sf = tk.Frame(self.root, bg=BG)
        sf.pack(fill="x", padx=20, pady=(4, 8))

        search_container = tk.Frame(sf, bg=SEARCH_BG)
        search_container.pack(fill="x", padx=4)
        
        self.search_var = tk.StringVar()
        self._search_entry = tk.Entry(
            search_container, textvariable=self.search_var,
            font=("Helvetica", 13), fg=FG_DIM, bg=SEARCH_BG,
            insertbackground=FG, relief="flat", bd=0,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(4, 0))
        
        # Shortcut hint
        shortcut_text = "⌘F" if IS_MAC else "Ctrl+F"
        tk.Label(search_container, text=shortcut_text, font=("Helvetica", 9),
                fg=FG_DIM, bg=SEARCH_BG).pack(side="right", padx=8)
        
        self._search_entry.insert(0, "Search skills...")
        self._search_has_focus = False

        def _focus_in(e):
            self._search_has_focus = True
            if self._search_entry.get() == "Search skills...":
                self._search_entry.delete(0, "end")
                self._search_entry.configure(fg=FG)

        def _focus_out(e):
            self._search_has_focus = False
            if not self._search_entry.get():
                self._search_entry.insert(0, "Search skills...")
                self._search_entry.configure(fg=FG_DIM)

        self._search_entry.bind("<FocusIn>", _focus_in)
        self._search_entry.bind("<FocusOut>", _focus_out)
        self.search_var.trace_add("write", self._on_search_changed)

        # Tab bar
        tab_frame = tk.Frame(self.root, bg=BG)
        tab_frame.pack(fill="x", padx=20, pady=(0, 4))

        self.tab_buttons = {}
        _tab_tips = {
            "all": "Show all skills", "installed": "Show installed skills only",
            "available": "Show uninstalled skills only",
            "discover": "Search GitHub for new skill repos",
            "sources": "Manage registry sources",
        }
        for label, key in [("All", "all"), ("Installed", "installed"),
                           ("Available", "available"),
                           ("🔍 Discover", "discover"), ("📚 Sources", "sources")]:
            btn = tk.Button(
                tab_frame, text=label, font=("Helvetica", 11),
                fg=FG, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
                relief="flat", cursor="hand2", bd=0, padx=14, pady=4,
                command=lambda k=key: self._set_filter(k),
            )
            btn.pack(side="left", padx=(0, 6))
            self.tab_buttons[key] = btn
            ToolTip(btn, _tab_tips[key])

        # Sort selector (right side of tab bar)
        self._sort_var = tk.StringVar(value="name")
        sort_frame = tk.Frame(tab_frame, bg=BG)
        sort_frame.pack(side="right")
        tk.Label(sort_frame, text="Sort:", font=("Helvetica", 9),
                 fg=FG_DIM, bg=BG).pack(side="left", padx=(0, 4))
        self._sort_buttons: dict[str, tk.Button] = {}
        _sort_tips = {
            "name": "Sort alphabetically by name",
            "risk": "Sort by scan severity (HIGH risk first)",
            "category": "Sort by category, then name",
        }
        for label, key in [("Name", "name"), ("⚠ Risk", "risk"), ("Category", "category")]:
            sb = tk.Button(
                sort_frame, text=label, font=("Helvetica", 9),
                fg=FG_DIM, bg=BG, activeforeground=FG, activebackground=BG_CARD,
                relief="flat", cursor="hand2", bd=0, padx=6, pady=2,
                command=lambda k=key: self._set_sort(k),
            )
            sb.pack(side="left", padx=(0, 2))
            self._sort_buttons[key] = sb
            ToolTip(sb, _sort_tips[key])

        # Category filter bar (horizontally scrollable)
        cat_outer = tk.Frame(self.root, bg=BG)
        cat_outer.pack(fill="x", padx=20, pady=(0, 4))
        self._cat_left_btn = tk.Button(
            cat_outer, text="◀", font=("Helvetica", 10), fg=FG_DIM, bg=BG,
            relief="flat", bd=0, padx=2, cursor="hand2",
            command=lambda: self._cat_canvas.xview_scroll(-3, "units"))
        self._cat_left_btn.pack(side="left")
        self._cat_right_btn = tk.Button(
            cat_outer, text="▶", font=("Helvetica", 10), fg=FG_DIM, bg=BG,
            relief="flat", bd=0, padx=2, cursor="hand2",
            command=lambda: self._cat_canvas.xview_scroll(3, "units"))
        self._cat_right_btn.pack(side="right")
        self._cat_canvas = tk.Canvas(cat_outer, bg=BG, highlightthickness=0, height=28)
        self._cat_canvas.pack(side="left", fill="x", expand=True)
        self._cat_frame = tk.Frame(self._cat_canvas, bg=BG)
        self._cat_canvas.create_window((0, 0), window=self._cat_frame, anchor="nw")
        self._cat_frame.bind("<Configure>", self._update_cat_arrows)
        self._cat_canvas.bind("<Configure>", self._update_cat_arrows)
        self._cat_buttons: dict[str, tk.Button] = {}

        # Status bar
        self.status_var = tk.StringVar(value="Loading...")
        self._task_var = tk.StringVar()
        status_frame = tk.Frame(self.root, bg=SEARCH_BG)
        status_frame.pack(fill="x", side="bottom")
        tk.Label(status_frame, textvariable=self.status_var,
                 font=("Helvetica", 10), fg=FG_DIM, bg=SEARCH_BG, anchor="w"
                 ).pack(side="left", padx=(16, 8), pady=4)
        self._task_label = tk.Label(
            status_frame, textvariable=self._task_var,
            font=("Helvetica", 10), fg=ACCENT, bg=SEARCH_BG, anchor="e")
        self._task_label.pack(side="right", padx=(8, 16), pady=4)

        # Batch action bar (hidden by default)
        self._batch_bar = tk.Frame(self.root, bg=SEARCH_BG)
        self._batch_count_var = tk.StringVar(value="0 selected")
        tk.Label(self._batch_bar, textvariable=self._batch_count_var,
                 font=("Helvetica", 11, "bold"), fg=FG, bg=SEARCH_BG
                 ).pack(side="left", padx=(12, 8))
        _b = tk.Button(
            self._batch_bar, text="☑ All", font=("Helvetica", 10),
            fg=ACCENT, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=8,
            command=self._batch_select_all,
        )
        _b.pack(side="left", padx=(0, 4))
        ToolTip(_b, "Select all skills on current page")
        _b = tk.Button(
            self._batch_bar, text="☐ None", font=("Helvetica", 10),
            fg=FG_DIM, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=8,
            command=self._batch_select_none,
        )
        _b.pack(side="left", padx=(0, 4))
        ToolTip(_b, "Deselect all skills")
        _b = tk.Button(
            self._batch_bar, text="⬇ Install All Visible", font=("Helvetica", 10, "bold"),
            fg=BG, bg=GREEN, activeforeground=BG, activebackground="#8bc98a",
            relief="flat", cursor="hand2", bd=0, padx=12, pady=4,
            command=self._install_all_visible,
        )
        _b.pack(side="left", padx=(8, 4))
        ToolTip(_b, "Install all uninstalled skills matching current filter")
        _b = tk.Button(
            self._batch_bar, text="🗑 Uninstall", font=("Helvetica", 10, "bold"),
            fg=RED, bg=SEARCH_BG, activeforeground=RED, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=10,
            command=self._batch_uninstall,
        )
        _b.pack(side="right", padx=(4, 12))
        ToolTip(_b, "Uninstall all selected skills")
        _b = tk.Button(
            self._batch_bar, text="🛡 Security Scan", font=("Helvetica", 10, "bold"),
            fg=ORANGE, bg=SEARCH_BG, activeforeground=ORANGE, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=10,
            command=self._batch_scan,
        )
        _b.pack(side="right", padx=(4, 4))
        ToolTip(_b, "Scan selected skills for malicious patterns (downloads uninstalled ones to temp)")
        _b = tk.Button(
            self._batch_bar, text="⬇ Install", font=("Helvetica", 10, "bold"),
            fg=BG, bg=ACCENT, activeforeground=BG, activebackground="#6a9ae0",
            relief="flat", cursor="hand2", bd=0, padx=14, pady=4,
            command=self._batch_install,
        )
        _b.pack(side="right", padx=(4, 4))
        ToolTip(_b, "Install all selected uninstalled skills")
        # Don't pack yet — shown/hidden dynamically

        # Scrollable area
        self._scroll_container = tk.Frame(self.root, bg=BG)
        self._scroll_container.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        self.canvas = tk.Canvas(self._scroll_container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self._scroll_container, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=BG)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self._canvas_win = self.canvas.create_window(
            (0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # Cross-platform scroll
        if IS_MAC:
            self.canvas.bind_all("<MouseWheel>",
                                 lambda e: self.canvas.yview_scroll(-e.delta, "units"))
        else:
            self.canvas.bind_all("<MouseWheel>",
                                 lambda e: self.canvas.yview_scroll(
                                     -1 * (e.delta // 120), "units"))
            self.canvas.bind_all("<Button-4>",
                                 lambda e: self.canvas.yview_scroll(-3, "units"))
            self.canvas.bind_all("<Button-5>",
                                 lambda e: self.canvas.yview_scroll(3, "units"))

    def _on_canvas_resize(self, event):
        self._content_width = event.width
        self.canvas.itemconfig(self._canvas_win, width=event.width)
        for card in self._cards:
            if hasattr(card, "update_wraplength"):
                card.update_wraplength(event.width)
        if self._info_label:
            try:
                self._info_label.configure(wraplength=max(300, event.width - 60))
            except tk.TclError:
                self._info_label = None

    # ── Debounced Search ───────────────────────────────────────

    def _on_search_changed(self, *_):
        """Debounce search: wait 300ms after last keystroke before rendering."""
        if self._debounce_id is not None:
            self.root.after_cancel(self._debounce_id)
        # Don't trigger on placeholder text
        val = self.search_var.get()
        if val == "Search skills..." and not self._search_has_focus:
            return
        self._debounce_id = self.root.after(300, self._render_content)

    # ── Category Filter ────────────────────────────────────────

    def _rebuild_category_bar(self):
        """Rebuild category chip bar from current skills."""
        for w in self._cat_frame.winfo_children():
            w.destroy()
        self._cat_buttons.clear()

        # Only show in skill-list tabs
        if self.current_filter in ("discover", "sources"):
            return

        cats = skilldb.get_categories()
        if len(cats) <= 1:
            return

        btn_all = tk.Button(
            self._cat_frame, text="All", font=("Helvetica", 10),
            fg=FG, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
            relief="flat", cursor="hand2", bd=0, padx=10, pady=2,
            command=lambda: self._set_category(""),
        )
        btn_all.pack(side="left", padx=(0, 4))
        self._cat_buttons[""] = btn_all

        for cat in cats:
            btn = tk.Button(
                self._cat_frame, text=cat, font=("Helvetica", 10),
                fg=FG, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
                relief="flat", cursor="hand2", bd=0, padx=10, pady=2,
                command=lambda c=cat: self._set_category(c),
            )
            btn.pack(side="left", padx=(0, 4))
            self._cat_buttons[cat] = btn

        self._highlight_category()

    def _set_category(self, cat: str):
        self.current_category = cat
        self._highlight_category()
        self._render_content()

    def _set_sort(self, key: str):
        self.current_sort = key
        for k, sb in self._sort_buttons.items():
            sb.configure(fg=(ACCENT if k == key else FG_DIM))
        self._render_content()

    def _highlight_category(self):
        for c, btn in self._cat_buttons.items():
            if c == self.current_category:
                btn.configure(bg=ACCENT, fg=BG)
            else:
                btn.configure(bg=SEARCH_BG, fg=FG)

    def _update_cat_arrows(self, *_):
        """Show/hide ◀▶ arrows based on whether category bar overflows."""
        self._cat_canvas.configure(scrollregion=self._cat_canvas.bbox("all") or (0, 0, 0, 0))
        fw = self._cat_frame.winfo_reqwidth()
        cw = self._cat_canvas.winfo_width()
        overflow = fw > cw
        self._cat_left_btn.configure(fg=FG_DIM if overflow else BG)
        self._cat_right_btn.configure(fg=FG_DIM if overflow else BG)
        if not hasattr(self, "_cat_scroll_bound"):
            self._cat_scroll_bound = True
            self._cat_canvas.bind("<Button-4>",
                lambda e: self._cat_canvas.xview_scroll(-3, "units"))
            self._cat_canvas.bind("<Button-5>",
                lambda e: self._cat_canvas.xview_scroll(3, "units"))
            self._cat_frame.bind("<Button-4>",
                lambda e: self._cat_canvas.xview_scroll(-3, "units"))
            self._cat_frame.bind("<Button-5>",
                lambda e: self._cat_canvas.xview_scroll(3, "units"))

    # ── Data & Rendering ───────────────────────────────────────

    def _refresh_registry(self):
        self.status_var.set("⏳ Fetching skill registry...")

        def _fetch():
            skills = fetch_registry(timeout=8)
            self.all_skills = skills
            self.root.after(0, self._on_registry_loaded)

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_registry_loaded(self):
        self._rebuild_category_bar()
        self._render_content()

    def _set_filter(self, key: str):
        self.current_filter = key
        for k, btn in self.tab_buttons.items():
            btn.configure(bg=(ACCENT if k == key else SEARCH_BG),
                          fg=(BG if k == key else FG))
        self._rebuild_category_bar()
        if key == "discover":
            self._do_discover()
        else:
            self._render_content()

    def _render_content(self, *_):
        if self.current_filter == "discover":
            self._hide_batch_bar()
            self._render_discover()
        elif self.current_filter == "sources":
            self._hide_batch_bar()
            self._render_sources()
        else:
            self._page = 0
            self._render_skills()

    def _hide_batch_bar(self):
        if self._batch_bar and self._batch_bar.winfo_ismapped():
            self._batch_bar.pack_forget()
        self._check_vars.clear()

    def _get_search_query(self) -> str:
        val = self.search_var.get()
        if val == "Search skills...":
            return ""
        return val

    def _render_skills(self, *_):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self._cards.clear()
        self._info_label = None

        # Paginated query from SQLite
        query = self._get_search_query()
        skills, total = skilldb.query_skills(
            query=query, category=self.current_category,
            filter_type=self.current_filter, sort=self.current_sort,
            offset=self._page * self._page_size, limit=self._page_size,
        )
        self._total_skills = total
        stats = skilldb.get_stats()

        status = (f"📦 {stats['total']} skills  ·  "
                  f"✓ {stats['installed']} installed  ·  "
                  f"Showing {self._page * self._page_size + 1}-"
                  f"{min((self._page + 1) * self._page_size, total)} of {total}")
        if stats["scanned"]:
            status += f"  ·  🔍 {stats['scanned']} scanned"
        if stats["high_risk"]:
            status += f"  ·  🔴 {stats['high_risk']} high-risk"
        self.status_var.set(status)

        if not skills:
            self._update_batch_bar()
            tk.Label(self.scroll_frame, text="No skills found.",
                     font=("Helvetica", 13), fg=FG_DIM, bg=BG).pack(pady=40)
            return

        for skill in skills:
            var = self._check_vars.get(skill["id"])
            if var is None:
                var = tk.BooleanVar(value=False)
                self._check_vars[skill["id"]] = var

            # Build snapshot-compatible info for SkillCard
            snap_entry = {}
            if skill.get("_installed"):
                snap_entry[skill["id"]] = {"version": skill.get("_inst_version", "")}
            card = SkillCard(self.scroll_frame, skill, self._handle_action,
                             snap_entry, var, scan_result=skill.get("_scan"))
            card.pack(fill="x", pady=(0, 8))
            card.update_wraplength(self._content_width)
            self._cards.append(card)

        # Pagination bar
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        if total_pages > 1:
            pbar = tk.Frame(self.scroll_frame, bg=BG)
            pbar.pack(fill="x", pady=(8, 4))

            if self._page > 0:
                tk.Button(pbar, text="◀ Prev", font=("Helvetica", 10),
                          fg=ACCENT, bg=SEARCH_BG, relief="flat", cursor="hand2",
                          bd=0, padx=12, pady=4,
                          command=self._prev_page).pack(side="left")

            tk.Label(pbar, text=f"Page {self._page + 1} / {total_pages}",
                     font=("Helvetica", 10), fg=FG_DIM, bg=BG).pack(side="left", padx=12)

            if self._page < total_pages - 1:
                tk.Button(pbar, text="Next ▶", font=("Helvetica", 10),
                          fg=ACCENT, bg=SEARCH_BG, relief="flat", cursor="hand2",
                          bd=0, padx=12, pady=4,
                          command=self._next_page).pack(side="left")

        self._update_batch_bar()
        self.canvas.yview_moveto(0)

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render_skills()

    def _next_page(self):
        total_pages = (self._total_skills + self._page_size - 1) // self._page_size
        if self._page < total_pages - 1:
            self._page += 1
            self._render_skills()

    # ── Discover Tab ───────────────────────────────────────────

    def _do_discover(self):
        self.status_var.set("🔍 Searching GitHub for skill repos...")
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self._cards.clear()

        tk.Label(self.scroll_frame,
                 text="🔍 Searching GitHub for skill repositories...",
                 font=("Helvetica", 13), fg=FG_DIM, bg=BG).pack(pady=40)

        def _search():
            repos = discover_github_repos(timeout=10)
            self.discovered_repos = repos
            self.root.after(0, self._render_discover)

        threading.Thread(target=_search, daemon=True).start()

    def _render_discover(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self._cards.clear()

        repos = self.discovered_repos
        query = self._get_search_query().lower()
        if query:
            repos = [r for r in repos if query in (
                r.get("name", "") + r.get("description", "") + r.get("repo", "")
            ).lower()]

        self.status_var.set(
            f"🔍 Discovered {len(self.discovered_repos)} repos  ·  "
            f"Showing {len(repos)}"
        )

        if not repos:
            cached = get_cached_discoveries()
            if cached and not self.discovered_repos:
                self.discovered_repos = cached
                self._render_discover()
                return
            tk.Label(self.scroll_frame,
                     text="No repos discovered. Check network or try again.",
                     font=("Helvetica", 13), fg=FG_DIM, bg=BG).pack(pady=40)
            return

        # Info banner
        info = tk.Frame(self.scroll_frame, bg=BG_CARD,
                        highlightbackground=ACCENT, highlightthickness=1)
        info.pack(fill="x", pady=(0, 12))
        self._info_label = tk.Label(
            info,
            text="💡 Repos found on GitHub, filtered by relevance. "
                 "Click 'Add & Scan' to import skills.",
            font=("Helvetica", 10), fg=FG_DIM, bg=BG_CARD,
            wraplength=600, justify="left",
        )
        self._info_label.pack(padx=12, pady=8)

        for repo in repos:
            card = RepoCard(self.scroll_frame, repo, self._handle_discover_action)
            card.pack(fill="x", pady=(0, 8))
            card.update_wraplength(self._content_width)
            self._cards.append(card)

        self.canvas.yview_moveto(0)

    def _handle_discover_action(self, action: str, repo: dict):
        if action == "add_source":
            self._add_and_scan_repo(repo)

    def _add_and_scan_repo(self, repo: dict):
        self.status_var.set(f"📡 Scanning {repo['repo']}...")

        def _scan():
            add_source_to_registry(
                repo["repo"], repo.get("name", repo["repo"]), repo.get("url", ""))
            skills = fetch_skills_from_github_repo(repo["repo"], timeout=15)
            added = merge_discovered_skills(skills) if skills else 0
            new_skills = fetch_registry(timeout=5)

            def _done():
                self.all_skills = new_skills
                if added > 0:
                    messagebox.showinfo(
                        "Skills Imported",
                        f"Added {added} skills from {repo['repo']}",
                        parent=self.root)
                else:
                    messagebox.showinfo(
                        "Source Added",
                        f"{repo['repo']} added as source.\n"
                        f"No SKILL.md files found to auto-import.",
                        parent=self.root)
                self._render_content()
            self.root.after(0, _done)

        threading.Thread(target=_scan, daemon=True).start()

    # ── Sources Tab (enhanced) ─────────────────────────────────

    def _render_sources(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self._cards.clear()

        sources = get_registry_sources()
        self.status_var.set(f"📚 {len(sources)} registered skill sources")

        # Add source input bar
        add_frame = tk.Frame(self.scroll_frame, bg=BG_CARD,
                             highlightbackground=ACCENT, highlightthickness=1)
        add_frame.pack(fill="x", pady=(0, 12))

        add_row = tk.Frame(add_frame, bg=BG_CARD)
        add_row.pack(fill="x", padx=12, pady=8)

        tk.Label(add_row, text="Add source:", font=("Helvetica", 11),
                 fg=FG, bg=BG_CARD).pack(side="left")

        self._add_source_var = tk.StringVar()
        add_entry = tk.Entry(
            add_row, textvariable=self._add_source_var,
            font=("Helvetica", 11), fg=FG, bg=SEARCH_BG,
            insertbackground=FG, relief="flat", bd=0, width=35,
        )
        add_entry.pack(side="left", padx=(8, 8), ipady=4)
        add_entry.insert(0, "owner/repo")
        add_entry.bind("<FocusIn>", lambda e: (
            add_entry.delete(0, "end") if add_entry.get() == "owner/repo" else None,
            add_entry.configure(fg=FG),
        ))
        add_entry.bind("<FocusOut>", lambda e: (
            (add_entry.insert(0, "owner/repo"), add_entry.configure(fg=FG_DIM))
            if not add_entry.get() else None
        ))
        add_entry.configure(fg=FG_DIM)

        tk.Button(
            add_row, text="➕ Add", font=("Helvetica", 10, "bold"),
            fg=BG, bg=GREEN, activeforeground=BG, activebackground="#8bc98a",
            relief="flat", cursor="hand2", bd=0, padx=12, pady=4,
            command=self._add_source_manual,
        ).pack(side="left")

        if not sources:
            tk.Label(self.scroll_frame, text="No sources registered yet.",
                     font=("Helvetica", 13), fg=FG_DIM, bg=BG).pack(pady=40)
            return

        # Scan All button bar
        scan_bar = tk.Frame(self.scroll_frame, bg=BG)
        scan_bar.pack(fill="x", pady=(0, 8))
        tk.Label(scan_bar, text="Registered Skill Repositories",
                 font=("Helvetica", 14, "bold"), fg=FG, bg=BG,
                 anchor="w").pack(side="left")
        tk.Button(
            scan_bar, text="🔄 Scan All Sources", font=("Helvetica", 10, "bold"),
            fg=BG, bg=ACCENT, activeforeground=BG, activebackground="#6a9ae0",
            relief="flat", cursor="hand2", bd=0, padx=14, pady=4,
            command=lambda: self._scan_all_sources(sources),
        ).pack(side="right")

        for source in sources:
            card = SourceCard(self.scroll_frame, source, self._handle_source_action)
            card.pack(fill="x", pady=(0, 4))
            self._cards.append(card)

        self.canvas.yview_moveto(0)

    def _add_source_manual(self):
        repo = self._add_source_var.get().strip()
        if not repo or repo == "owner/repo" or "/" not in repo:
            messagebox.showwarning("Invalid", "Enter a valid GitHub repo (owner/repo)",
                                   parent=self.root)
            return
        name = repo.split("/")[-1]
        url = f"https://github.com/{repo}"
        add_source_to_registry(repo, name, url)
        self._add_source_var.set("")
        # Scan it
        self._add_and_scan_repo({"repo": repo, "name": name, "url": url})

    def _handle_source_action(self, action: str, source: dict):
        if action == "remove":
            repo = source.get("repo", "")
            if messagebox.askyesno("Confirm", f"Remove source {repo}?",
                                    parent=self.root):
                remove_source_from_registry(repo)
                self._render_sources()
        elif action == "rescan":
            repo = source.get("repo", "")
            self.status_var.set(f"🔄 Rescanning {repo}...")

            def _rescan():
                skills = fetch_skills_from_github_repo(repo, timeout=15)
                added = merge_discovered_skills(skills) if skills else 0
                new_skills = fetch_registry(timeout=5)

                def _done():
                    self.all_skills = new_skills
                    messagebox.showinfo(
                        "Rescan Complete",
                        f"Found {len(skills)} skills, {added} new.",
                        parent=self.root)
                    self._render_sources()
                self.root.after(0, _done)

            threading.Thread(target=_rescan, daemon=True).start()

    def _scan_all_sources(self, sources: list[dict]):
        """Scan all registered sources with a progress dialog."""
        total = len(sources)
        if total == 0:
            return

        pw = tk.Toplevel(self.root)
        pw.title(f"Scanning All Sources ({total})")
        pw.geometry("460x160")
        pw.configure(bg=BG)
        pw.resizable(False, False)
        pw.transient(self.root)
        pw.grab_set()

        title_var = tk.StringVar(value=f"Scanning 1/{total}...")
        tk.Label(pw, textvariable=title_var,
                 font=("Helvetica", 13, "bold"), fg=FG, bg=BG).pack(pady=(14, 4))

        pv = tk.DoubleVar()
        ttk.Progressbar(pw, variable=pv, maximum=100, length=400).pack(padx=20, pady=(0, 6))

        msg_var = tk.StringVar(value="Starting...")
        tk.Label(pw, textvariable=msg_var, font=("Helvetica", 10),
                 fg=FG_DIM, bg=BG).pack()

        def _run():
            total_added = 0
            total_found = 0
            for i, src in enumerate(sources):
                repo = src.get("repo", "")
                self.root.after(0, lambda i=i, r=repo: title_var.set(
                    f"Scanning {i + 1}/{total}: {r}"))
                self.root.after(0, lambda i=i: pv.set((i / total) * 100))
                self.root.after(0, lambda r=repo: msg_var.set(f"Fetching {r}..."))
                try:
                    skills = fetch_skills_from_github_repo(repo, timeout=15)
                    total_found += len(skills)
                    added = merge_discovered_skills(skills) if skills else 0
                    total_added += added
                except Exception:
                    pass

            new_skills = fetch_registry(timeout=5)
            self.root.after(0, lambda: pv.set(100))

            def _done():
                pw.destroy()
                self.all_skills = new_skills
                messagebox.showinfo(
                    "Scan All Complete",
                    f"Scanned {total} sources\n"
                    f"Found {total_found} skills, {total_added} new added.",
                    parent=self.root)
                self._render_sources()

            self.root.after(300, _done)

        threading.Thread(target=_run, daemon=True).start()

    # ── Install / Uninstall ────────────────────────────────────

    def _handle_action(self, action: str, skill):
        if action == "install":
            self._do_install(skill)
        elif action == "uninstall":
            self._do_uninstall(skill)
        elif action == "scan":
            self._do_scan_skill(skill)
        elif action == "scan_details":
            self._show_scan_details(skill)
        elif action == "_selection_changed":
            self._update_batch_bar()

    # ── Batch Selection ────────────────────────────────────────

    def _get_selected_skills(self) -> list[dict]:
        """Return list of skill dicts whose checkbox is checked."""
        selected_ids = {sid for sid, var in self._check_vars.items() if var.get()}
        if not selected_ids:
            return []
        # Fetch all matching from DB (no pagination limit)
        skills, _ = skilldb.query_skills(
            query=self._get_search_query(), category=self.current_category,
            filter_type=self.current_filter, sort=self.current_sort,
            offset=0, limit=9999,
        )
        return [s for s in skills if s["id"] in selected_ids]

    def _update_batch_bar(self):
        """Show/hide the batch action bar. Always visible on skill tabs for Install All."""
        count = sum(1 for v in self._check_vars.values() if v.get())
        if self.current_filter not in ("discover", "sources"):
            self._batch_count_var.set(f"{count} selected" if count else "Batch actions")
            if not self._batch_bar.winfo_ismapped():
                self._batch_bar.pack(fill="x", padx=20, pady=(0, 4),
                                     before=self._scroll_container)
        else:
            if self._batch_bar.winfo_ismapped():
                self._batch_bar.pack_forget()

    def _batch_select_all(self):
        for var in self._check_vars.values():
            var.set(True)
        self._update_batch_bar()

    def _batch_select_none(self):
        for var in self._check_vars.values():
            var.set(False)
        self._update_batch_bar()

    def _install_all_visible(self):
        """Install all visible uninstalled skills (no checkbox needed)."""
        skills, _ = skilldb.query_skills(
            query=self._get_search_query(), category=self.current_category,
            filter_type="available", sort=self.current_sort,
            offset=0, limit=9999,
        )
        to_install = skills
        if not to_install:
            messagebox.showinfo("Nothing to install",
                                "All visible skills are already installed.",
                                parent=self.root)
            return
        names = ", ".join(s["name"] for s in to_install[:5])
        if len(to_install) > 5:
            names += f" ... +{len(to_install) - 5} more"
        if not messagebox.askyesno(
            "Install All Visible",
            f"Install {len(to_install)} skills?\n\n{names}",
            parent=self.root,
        ):
            return
        self._do_batch_install(to_install)

    def _batch_install(self):
        selected = self._get_selected_skills()
        to_install = [s for s in selected if not s.get("_installed")]
        if not to_install:
            messagebox.showinfo("Nothing to install",
                                "All selected skills are already installed.",
                                parent=self.root)
            return
        names = ", ".join(s["name"] for s in to_install[:5])
        if len(to_install) > 5:
            names += f" ... +{len(to_install) - 5} more"
        if not messagebox.askyesno(
            "Batch Install",
            f"Install {len(to_install)} skills?\n\n{names}",
            parent=self.root,
        ):
            return
        self._do_batch_install(to_install)

    def _batch_uninstall(self):
        selected = self._get_selected_skills()
        to_remove = [s for s in selected if s.get("_installed")]
        if not to_remove:
            messagebox.showinfo("Nothing to uninstall",
                                "None of the selected skills are installed.",
                                parent=self.root)
            return
        names = ", ".join(s["name"] for s in to_remove[:5])
        if len(to_remove) > 5:
            names += f" ... +{len(to_remove) - 5} more"
        if not messagebox.askyesno(
            "Batch Uninstall",
            f"Uninstall {len(to_remove)} skills?\n\n{names}",
            parent=self.root,
        ):
            return
        self._do_batch_uninstall(to_remove)

    def _batch_scan(self):
        """Scan selected skills (installed locally, uninstalled via temp download)."""
        selected = self._get_selected_skills()
        if not selected:
            messagebox.showinfo("Nothing to scan",
                                "No skills selected. Use the checkbox to select skills.",
                                parent=self.root)
            return
        # Split into installed (local scan) and uninstalled (remote scan)
        local = [s for s in selected if s.get("_installed")]
        remote = [s for s in selected if not s.get("_installed")]
        no_source = [s for s in remote if not s.get("repo") and not s.get("url")]
        remote = [s for s in remote if s.get("repo") or s.get("url")]

        if no_source and not local and not remote:
            messagebox.showinfo("Cannot scan",
                                "Selected skills have no download source.",
                                parent=self.root)
            return

        msg_parts = []
        if local:
            msg_parts.append(f"• {len(local)} installed (local scan)")
        if remote:
            msg_parts.append(f"• {len(remote)} not installed (download → scan → discard)")
        if no_source:
            msg_parts.append(f"• {len(no_source)} skipped (no download source)")
        detail = "\n".join(msg_parts)

        if remote:
            if not messagebox.askyesno(
                "Scan Skills",
                f"{detail}\n\nUninstalled skills will be downloaded to a "
                "temporary directory for scanning only. Continue?",
                parent=self.root,
            ):
                return

        self._do_batch_scan(local, remote)

    def _do_batch_scan(self, local: list[dict], remote: list[dict] | None = None):
        """Scan skills with tracker dialog. Local = installed, remote = download first."""
        remote = remote or []
        all_skills = local + remote
        total = len(all_skills)
        remote_ids = {s["id"] for s in remote}

        tracker = ScanTracker(self.root, f"Scanning {total} Skills")
        self._task_var.set(f"🔍 Scanning {total} skills...")

        def _run():
            high = clean = failed = 0
            for i, skill in enumerate(all_skills):
                is_rem = skill["id"] in remote_ids
                prefix = "⬇ " if is_rem else ""
                self.root.after(0, lambda i=i, n=skill["name"], p=prefix:
                    (tracker.set_progress(i + 1, total, f"{p}{n}"),))

                if is_rem:
                    self.root.after(0, lambda n=skill["name"]:
                        tracker.log(f"⬇ Downloading {n}...", "info"))
                    r = scan_remote_skill(skill)
                else:
                    r = scan_single_skill(skill["id"])

                def _log_result(r=r, name=skill["name"]):
                    if r:
                        fc = r["findings_count"]
                        sev = r["severity"]
                        tag = {"HIGH": "high", "MEDIUM": "med", "LOW": "low"}.get(sev, "ok")
                        if fc == 0:
                            tracker.log(f"🟢 {name}: clean", "ok")
                        else:
                            cats = ", ".join(r.get("categories", []))
                            icon = "🔴" if sev == "HIGH" else "🟡" if sev == "MEDIUM" else "🔵"
                            tracker.log(f"{icon} {name}: {sev} — {fc} finding(s) [{cats}]", tag)
                    else:
                        tracker.log(f"✗ {name}: failed", "fail")
                self.root.after(0, _log_result)

                if r:
                    if r["severity"] == "HIGH": high += 1
                    if r["findings_count"] == 0: clean += 1
                else:
                    failed += 1

            def _done():
                self._task_var.set("")
                self._batch_select_none()
                summary = f"🟢 {clean} clean · 🔴 {high} high-risk"
                if failed:
                    summary += f" · ⚠ {failed} failed"
                tracker.finish(summary)
                tracker.on_finish(self._render_content)
            self.root.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _do_batch_install(self, skills: list[dict]):
        """Install multiple skills sequentially with a progress dialog."""
        total = len(skills)
        pw = tk.Toplevel(self.root)
        pw.title(f"Batch Install ({total} skills)")
        pw.geometry("460x180")
        pw.configure(bg=BG)
        pw.resizable(False, False)
        pw.transient(self.root)
        pw.grab_set()

        title_var = tk.StringVar(value=f"Installing 1/{total}...")
        tk.Label(pw, textvariable=title_var,
                 font=("Helvetica", 13, "bold"), fg=FG, bg=BG).pack(pady=(14, 4))

        # Overall progress
        overall_var = tk.DoubleVar()
        ttk.Progressbar(pw, variable=overall_var, maximum=100,
                        length=400).pack(padx=20, pady=(0, 6))

        # Current item progress
        item_var = tk.DoubleVar()
        ttk.Progressbar(pw, variable=item_var, maximum=100,
                        length=400).pack(padx=20, pady=(0, 4))

        msg_var = tk.StringVar(value="Starting...")
        tk.Label(pw, textvariable=msg_var, font=("Helvetica", 10),
                 fg=FG_DIM, bg=BG).pack()

        def _run():
            ok_count = 0
            fail_count = 0
            for i, skill in enumerate(skills):
                self.root.after(0, lambda i=i: title_var.set(
                    f"Installing {i + 1}/{total}: {skills[i]['name']}"))
                self.root.after(0, lambda i=i: overall_var.set(
                    (i / total) * 100))
                self.root.after(0, lambda: item_var.set(0))

                def item_cb(pct, m):
                    self.root.after(0, lambda: item_var.set(pct))
                    self.root.after(0, lambda: msg_var.set(m))

                ok, _ = install_skill(skill, item_cb)
                if ok:
                    ok_count += 1
                else:
                    fail_count += 1

            self.root.after(0, lambda: overall_var.set(100))

            def _done():
                pw.destroy()
                self._batch_select_none()
                self._render_content()
                summary = f"✓ {ok_count} installed"
                if fail_count:
                    summary += f",  ✗ {fail_count} failed"
                messagebox.showinfo("Batch Install Complete", summary,
                                    parent=self.root)

            self.root.after(300, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _do_batch_uninstall(self, skills: list[dict]):
        total = len(skills)
        self.status_var.set(f"🗑 Uninstalling {total} skills...")

        def _run():
            ok_count = 0
            for i, skill in enumerate(skills):
                self.root.after(0, lambda i=i, n=skill["name"]:
                    self.status_var.set(f"🗑 Uninstalling {i+1}/{total}: {n}..."))
                ok, _ = uninstall_skill(skill["id"])
                if ok:
                    ok_count += 1

            def _done():
                self._batch_select_none()
                self._render_content()
                messagebox.showinfo("Batch Uninstall Complete",
                                    f"✓ {ok_count}/{total} uninstalled",
                                    parent=self.root)
            self.root.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _do_install(self, skill: dict):
        pw = tk.Toplevel(self.root)
        pw.title(f"Installing {skill['name']}")
        pw.geometry("420x150")
        pw.configure(bg=BG)
        pw.resizable(False, False)
        pw.transient(self.root)
        pw.grab_set()

        tk.Label(pw, text=f"Installing {skill['name']}...",
                 font=("Helvetica", 13, "bold"), fg=FG, bg=BG).pack(pady=(16, 8))
        pv = tk.DoubleVar()
        ttk.Progressbar(pw, variable=pv, maximum=100, length=360).pack(padx=20, pady=(0, 8))
        mv = tk.StringVar(value="Starting...")
        tk.Label(pw, textvariable=mv, font=("Helvetica", 10), fg=FG_DIM, bg=BG).pack()

        def cb(pct, msg):
            self.root.after(0, lambda: pv.set(pct))
            self.root.after(0, lambda: mv.set(msg))

        def _run():
            ok, msg = install_skill(skill, cb)
            def _done():
                pw.destroy()
                self._render_content()
                if ok:
                    ToastNotification(self.root, f"✓ Installed {skill['name']}")
                else:
                    messagebox.showerror("Error", msg, parent=self.root)
            self.root.after(200, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _do_uninstall(self, skill: dict):
        if not messagebox.askyesno("Confirm", f"Uninstall {skill['name']}?",
                                    parent=self.root):
            return
        self.status_var.set(f"🗑 Uninstalling {skill['name']}...")

        def _run():
            ok, msg = uninstall_skill(skill["id"])
            def _done():
                self._render_content()
                if ok:
                    ToastNotification(self.root, f"✓ Uninstalled {skill['name']}")
                else:
                    messagebox.showerror("Error", msg, parent=self.root)
            self.root.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _do_scan_skill(self, skill: dict):
        """Scan a single skill with tracker dialog."""
        installed = skill.get("_installed", False)
        mode = "local" if installed else "remote"
        tracker = ScanTracker(self.root, f"Scan: {skill['name']}")
        tracker.set_progress(0, 1, skill["name"])
        self._task_var.set(f"🔍 Scanning {skill['name']}...")

        if not installed:
            tracker.log(f"⬇ Downloading {skill['name']}...", "info")

        def _run():
            if installed:
                result = scan_single_skill(skill["id"])
            else:
                result = scan_remote_skill(skill)

            def _done():
                self._task_var.set("")
                if result:
                    fc = result["findings_count"]
                    sev = result["severity"]
                    tag = {"HIGH": "high", "MEDIUM": "med", "LOW": "low"}.get(sev, "ok")
                    if fc == 0:
                        tracker.log(f"🟢 {skill['name']}: clean — no issues", "ok")
                    else:
                        cats = ", ".join(result.get("categories", []))
                        tracker.log(f"{'🔴' if sev=='HIGH' else '🟡' if sev=='MEDIUM' else '🔵'} "
                                    f"{skill['name']}: {sev} — {fc} finding(s) [{cats}]", tag)
                        for f in result.get("findings", []):
                            tracker.log(f"   {f['severity']:6s} {f['name']} "
                                        f"({f['file']}:{f['line']})", tag)
                    tracker.set_progress(1, 1)
                    tracker.finish(f"{sev} — {fc} finding(s)")
                else:
                    tracker.log(f"✗ Could not scan {skill['name']}", "fail")
                    tracker.finish("Failed")
                tracker.on_finish(self._render_content)
            self.root.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _show_scan_details(self, skill: dict):
        """Show scan findings in a detail dialog."""
        sr = get_skill_scan(skill["id"])
        if not sr or not sr.get("findings"):
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Scan: {skill['name']}")
        dlg.geometry("560x400")
        dlg.configure(bg=BG)
        dlg.transient(self.root)

        # Header
        sev = sr["severity"]
        sev_colors = {"HIGH": RED, "MEDIUM": YELLOW, "LOW": ACCENT, "NONE": GREEN}
        hdr = tk.Frame(dlg, bg=BG)
        hdr.pack(fill="x", padx=16, pady=(12, 8))
        tk.Label(hdr, text=f"{skill['name']}", font=("Helvetica", 14, "bold"),
                 fg=FG, bg=BG).pack(side="left")
        tk.Label(hdr, text=f"  {sev}  ", font=("Helvetica", 10, "bold"),
                 fg=BG, bg=sev_colors.get(sev, FG_DIM)).pack(side="left", padx=(8, 0))
        tk.Label(hdr, text=f"{sr['findings_count']} findings  ·  {sr.get('timestamp', '')}",
                 font=("Helvetica", 9), fg=FG_DIM, bg=BG).pack(side="right")

        # Findings list (scrollable)
        txt = tk.Text(dlg, bg=BG_CARD, fg=FG, font=("Courier", 10),
                      relief="flat", wrap="word", padx=12, pady=8)
        sb = ttk.Scrollbar(dlg, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=(0, 8))
        txt.pack(fill="both", expand=True, padx=(16, 0), pady=(0, 8))

        txt.tag_configure("high", foreground=RED)
        txt.tag_configure("medium", foreground=YELLOW)
        txt.tag_configure("low", foreground=ACCENT)
        txt.tag_configure("dim", foreground=FG_DIM)

        for f in sr["findings"]:
            tag = f["severity"].lower()
            txt.insert("end", f"[{f['severity']}] ", tag)
            txt.insert("end", f"{f['id']}: {f['name']}\n")
            txt.insert("end", f"  File: {f['file']}:{f['line']}\n", "dim")
            txt.insert("end", f"  {f['match']}\n\n", "dim")

        txt.configure(state="disabled")

        # Close + Rescan buttons
        bot = tk.Frame(dlg, bg=BG)
        bot.pack(fill="x", padx=16, pady=(0, 12))
        tk.Button(bot, text="Close", font=("Helvetica", 10),
                  fg=FG, bg=SEARCH_BG, relief="flat", cursor="hand2", padx=14, pady=4,
                  command=dlg.destroy).pack(side="right")
        tk.Button(bot, text="🔍 Rescan", font=("Helvetica", 10),
                  fg=ORANGE, bg=SEARCH_BG, relief="flat", cursor="hand2", padx=14, pady=4,
                  command=lambda: (dlg.destroy(), self._do_scan_skill(skill))
                  ).pack(side="right", padx=(0, 8))

    def _do_scan_all(self):
        """Scan all installed skills with tracker dialog."""
        snap = get_installed_snapshot()
        total = len(snap)
        if total == 0:
            messagebox.showinfo("Nothing to scan", "No installed skills.",
                                parent=self.root)
            return

        tracker = ScanTracker(self.root, f"Scanning All ({total} Skills)")
        self._task_var.set(f"🔍 Scanning all {total} skills...")

        def _run():
            high = clean = 0
            for i, skill_id in enumerate(snap):
                name = snap[skill_id].get("name", skill_id)
                self.root.after(0, lambda i=i, n=name:
                    tracker.set_progress(i + 1, total, n))

                r = scan_single_skill(skill_id)

                def _log(r=r, n=name):
                    if r:
                        fc = r["findings_count"]
                        sev = r["severity"]
                        tag = {"HIGH": "high", "MEDIUM": "med", "LOW": "low"}.get(sev, "ok")
                        if fc == 0:
                            tracker.log(f"🟢 {n}: clean", "ok")
                        else:
                            icon = "🔴" if sev == "HIGH" else "🟡" if sev == "MEDIUM" else "🔵"
                            tracker.log(f"{icon} {n}: {sev} — {fc} finding(s)", tag)
                    else:
                        tracker.log(f"✗ {n}: failed", "fail")
                self.root.after(0, _log)

                if r:
                    if r["severity"] == "HIGH": high += 1
                    if r["findings_count"] == 0: clean += 1

            def _done():
                self._task_var.set("")
                summary = f"🟢 {clean} clean · 🔴 {high} high-risk"
                tracker.finish(summary)
                tracker.on_finish(self._render_content)
            self.root.after(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _show_proxy_settings(self):
        """Show proxy configuration dialog."""
        cfg = get_proxy_config()
        dlg = tk.Toplevel(self.root)
        dlg.title("Proxy Settings")
        dlg.geometry("440x240")
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.grab_set()

        enabled_var = tk.BooleanVar(value=cfg.get("enabled", False))
        http_var = tk.StringVar(value=cfg.get("http", ""))
        https_var = tk.StringVar(value=cfg.get("https", ""))

        tk.Label(dlg, text="Proxy Configuration", font=("Helvetica", 14, "bold"),
                 fg=FG, bg=BG).pack(pady=(16, 12))

        row1 = tk.Frame(dlg, bg=BG)
        row1.pack(fill="x", padx=24, pady=(0, 8))
        tk.Checkbutton(row1, text="Enable proxy", variable=enabled_var,
                       font=("Helvetica", 11), fg=FG, bg=BG, selectcolor=SEARCH_BG,
                       activebackground=BG, activeforeground=FG).pack(side="left")

        for label, var in [("HTTP Proxy:", http_var), ("HTTPS Proxy:", https_var)]:
            row = tk.Frame(dlg, bg=BG)
            row.pack(fill="x", padx=24, pady=(0, 6))
            tk.Label(row, text=label, font=("Helvetica", 10), fg=FG_DIM, bg=BG,
                     width=12, anchor="w").pack(side="left")
            tk.Entry(row, textvariable=var, font=("Helvetica", 11), fg=FG,
                     bg=SEARCH_BG, insertbackground=FG, relief="flat", bd=0
                     ).pack(side="left", fill="x", expand=True, ipady=4)

        tk.Label(dlg, text="e.g. http://127.0.0.1:7890", font=("Helvetica", 9),
                 fg=FG_DIM, bg=BG).pack(pady=(2, 8))

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=(0, 12))

        def _save():
            set_proxy_config(enabled_var.get(), http_var.get(), https_var.get())
            icon = "🌐" if enabled_var.get() else "⚙"
            self._proxy_btn.configure(text=f"{icon} Proxy")
            dlg.destroy()
            ToastNotification(self.root, "✓ Proxy settings saved")

        tk.Button(btn_row, text="Save", font=("Helvetica", 11, "bold"),
                  fg=BG, bg=ACCENT, activeforeground=BG, activebackground="#6a9ae0",
                  relief="flat", cursor="hand2", bd=0, padx=20, pady=4,
                  command=_save).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Cancel", font=("Helvetica", 11),
                  fg=FG_DIM, bg=SEARCH_BG, activeforeground=FG, activebackground=BG_CARD,
                  relief="flat", cursor="hand2", bd=0, padx=16, pady=4,
                  command=dlg.destroy).pack(side="left")

    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for common actions."""
        cmd_key = 'Command' if IS_MAC else 'Control'
        self.root.bind(f'<{cmd_key}-f>', lambda e: self._search_entry.focus_set())
        self.root.bind(f'<{cmd_key}-r>', lambda e: self._refresh_registry())
        self.root.bind(f'<{cmd_key}-i>', lambda e: self._set_filter('installed'))
        self.root.bind('<Escape>', lambda e: self._clear_search())
    
    def _clear_search(self):
        """Clear search field."""
        self.search_var.set("")
        if not self._search_has_focus:
            self._search_entry.delete(0, "end")
            self._search_entry.insert(0, "Search skills...")
            self._search_entry.configure(fg=FG_DIM)

    def run(self):
        self._set_filter("all")
        self.root.mainloop()


def main():
    """Entry point for console script."""
    SkillsManagerApp().run()


if __name__ == "__main__":
    main()
