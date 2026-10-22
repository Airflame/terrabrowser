"""Tkinter GUI for browsing potentially habitable exoplanets."""

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from . import api
from .habitability import (
    Planet, ZONE_COLD, ZONE_CONSERVATIVE, ZONE_HOT, ZONE_OPTIMISTIC,
)

BG = "#0e1320"
PANEL = "#161d2e"
PANEL_HI = "#1f2840"
BORDER = "#2a3550"
FG = "#e6e9f0"
MUTED = "#8b93a7"
ACCENT = "#5cc8ff"
SELECT = "#264b73"
EARTH = "#4f8cff"
ZONE_COLORS = {
    ZONE_CONSERVATIVE: "#4ade80",
    ZONE_OPTIMISTIC: "#a3e635",
    ZONE_HOT: "#f97316",
    ZONE_COLD: "#7dd3fc",
}
HZ_OPTIMISTIC_FILL = "#1b3a2a"
HZ_CONSERVATIVE_FILL = "#2c6a45"

FILTER_HZ = "Habitable zone (optimistic)"
FILTER_CONSERVATIVE = "Conservative habitable zone"
FILTER_ALL = "All small planets"

# (column id, heading, width, anchor, value getter, display formatter)
COLUMNS = [
    ("name", "Planet", 140, "w", lambda p: p.name, str),
    ("host", "Host star", 110, "w", lambda p: p.host, str),
    ("dist", "Dist. (ly)", 85, "e", lambda p: p.distance_ly, "{:,.1f}".format),
    ("radius", "Radius R⊕", 80, "e", lambda p: p.radius, "{:.2f}".format),
    ("mass", "Mass M⊕", 75, "e", lambda p: p.mass, "{:.2f}".format),
    ("insol", "Flux S⊕", 70, "e", lambda p: p.insolation, "{:.2f}".format),
    ("teq", "Teq (K)", 60, "e", lambda p: p.eq_temp, "{:.0f}".format),
    ("period", "Period (d)", 75, "e", lambda p: p.period, "{:,.1f}".format),
    ("zone", "Zone", 110, "w", lambda p: p.zone, str),
    ("esi", "ESI", 45, "e", lambda p: p.esi, "{:.2f}".format),
    ("year", "Year", 50, "e", lambda p: p.disc_year, str),
]
ESTIMATED_FIELD = {"radius": "radius", "insol": "insolation", "teq": "eq_temp"}


def star_color(teff: float | None) -> str:
    if teff is None:
        return "#ffffff"
    for limit, color in ((3500, "#ff8c5a"), (5000, "#ffb46b"), (6000, "#fff1c9"), (7500, "#f8f7ff")):
        if teff < limit:
            return color
    return "#bcd2ff"


def fmt(value, formatter, estimated: bool = False) -> str:
    if value is None:
        return "—"
    return ("~" if estimated else "") + formatter(value)


class TerraBrowser(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Terrabrowser — potentially habitable exoplanets")
        self.geometry("1400x820")
        self.minsize(1100, 640)
        self.configure(background=BG)

        self.planets: list[Planet] = []
        self.by_iid: dict[str, Planet] = {}
        self.selected: Planet | None = None
        self.sort_column = "esi"
        self.sort_descending = True
        self._results: queue.Queue = queue.Queue()

        self._setup_style()
        self._build_toolbar()
        self._build_statusbar()
        self._build_body()
        self.load(force_refresh=False)

    # ---- layout -------------------------------------------------------------------------------

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, bordercolor=BORDER,
                        lightcolor=PANEL, darkcolor=PANEL, troughcolor=PANEL, focuscolor=ACCENT,
                        selectbackground=SELECT, selectforeground=FG, insertcolor=FG,
                        font=("Segoe UI", 10))
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Panel.TLabel", background=PANEL)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Key.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Value.TLabel", background=PANEL, font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", background=PANEL, font=("Segoe UI", 18, "bold"))
        style.configure("Brand.TLabel", background=BG, foreground=ACCENT, font=("Segoe UI", 16, "bold"))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                        rowheight=26, borderwidth=0)
        style.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", FG)])
        style.configure("Treeview.Heading", background=PANEL_HI, foreground=FG, relief="flat",
                        font=("Segoe UI", 9, "bold"), padding=(6, 4))
        style.map("Treeview.Heading", background=[("active", BORDER)])
        style.configure("TButton", background=PANEL_HI, foreground=FG, padding=(10, 4), relief="flat")
        style.map("TButton", background=[("active", BORDER), ("disabled", PANEL)],
                  foreground=[("disabled", MUTED)])
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)], indicatorcolor=[("selected", ACCENT)])
        style.configure("TEntry", padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", SELECT)
        self.option_add("*TCombobox*Listbox.selectForeground", FG)
        style.configure("Vertical.TScrollbar", background=PANEL_HI, arrowcolor=MUTED)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(14, 12, 14, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="🪐 Terrabrowser", style="Brand.TLabel").pack(side="left", padx=(0, 20))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_table())
        ttk.Label(bar, text="Search").pack(side="left")
        ttk.Entry(bar, textvariable=self.search_var, width=22).pack(side="left", padx=(6, 16))

        self.zone_var = tk.StringVar(value=FILTER_HZ)
        ttk.Label(bar, text="Show").pack(side="left")
        zone_box = ttk.Combobox(bar, textvariable=self.zone_var, state="readonly", width=27,
                                values=[FILTER_HZ, FILTER_CONSERVATIVE, FILTER_ALL])
        zone_box.pack(side="left", padx=(6, 16))
        zone_box.bind("<<ComboboxSelected>>", lambda _: self.refresh_table())

        self.method_var = tk.StringVar(value="Any method")
        ttk.Label(bar, text="Discovery").pack(side="left")
        self.method_box = ttk.Combobox(bar, textvariable=self.method_var, state="readonly", width=24)
        self.method_box.pack(side="left", padx=(6, 16))
        self.method_box.bind("<<ComboboxSelected>>", lambda _: self.refresh_table())

        self.rocky_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Likely rocky only (R ≤ 1.6 R⊕)", variable=self.rocky_var,
                        command=self.refresh_table).pack(side="left")

        self.refresh_button = ttk.Button(bar, text="⟳ Refresh data", command=lambda: self.load(True))
        self.refresh_button.pack(side="right")

    def _build_body(self) -> None:
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 6))

        table_frame = ttk.Frame(body, style="Panel.TFrame")
        self.tree = ttk.Treeview(table_frame, columns=[c[0] for c in COLUMNS], show="headings",
                                 selectmode="browse")
        for col_id, heading, width, anchor, *_ in COLUMNS:
            self.tree.heading(col_id, text=heading, anchor=anchor,
                              command=lambda c=col_id: self.sort_by(c))
            self.tree.column(col_id, width=width, minwidth=40, anchor=anchor, stretch=True)
        for zone, color in ZONE_COLORS.items():
            self.tree.tag_configure(zone, foreground=color)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        body.add(table_frame, weight=3)

        body.add(self._build_detail_panel(body), weight=2)
        self.after(50, lambda: body.sashpos(0, max(self.winfo_width() - 540, 600)))

    def _build_detail_panel(self, parent) -> ttk.Frame:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        header = ttk.Frame(panel, style="Panel.TFrame")
        header.pack(fill="x")
        self.title_label = ttk.Label(header, text="Select a planet", style="Title.TLabel")
        self.title_label.pack(side="left")
        self.archive_button = ttk.Button(header, text="NASA Archive ↗", state="disabled",
                                         command=self._open_archive)
        self.archive_button.pack(side="right")
        self.subtitle_label = ttk.Label(panel, text="", style="Muted.TLabel")
        self.subtitle_label.pack(anchor="w")
        self.note_label = ttk.Label(panel, text="", style="Muted.TLabel", wraplength=480, justify="left")
        self.note_label.pack(anchor="w", pady=(2, 10))

        grid = ttk.Frame(panel, style="Panel.TFrame")
        grid.pack(fill="x")
        fields = [
            ("zone", "Habitable zone"), ("esi", "Earth similarity (ESI)"),
            ("size", "Size class"), ("radius", "Radius"),
            ("mass", "Mass"), ("insol", "Stellar flux"),
            ("teq", "Equilibrium temp."), ("period", "Orbital period"),
            ("sma", "Semi-major axis"), ("ecc", "Eccentricity"),
            ("star", "Star"), ("lum", "Star luminosity"),
            ("dist", "Distance"), ("system", "System"),
            ("disc", "Discovered"), ("coords", "RA / Dec"),
        ]
        self.detail_values: dict[str, ttk.Label] = {}
        for i, (key, label) in enumerate(fields):
            row, col = divmod(i, 2)
            cell = ttk.Frame(grid, style="Panel.TFrame")
            cell.grid(row=row, column=col, sticky="w", padx=(0, 16), pady=2)
            ttk.Label(cell, text=label.upper(), style="Key.TLabel").pack(anchor="w")
            value = ttk.Label(cell, text="—", style="Value.TLabel")
            value.pack(anchor="w")
            self.detail_values[key] = value
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        ttk.Label(panel, text="ORBIT VS. HABITABLE ZONE", style="Key.TLabel").pack(anchor="w", pady=(10, 2))
        self.hz_canvas = tk.Canvas(panel, height=110, background=BG, highlightthickness=0)
        self.hz_canvas.pack(fill="x")
        self.hz_canvas.bind("<Configure>", lambda _: self._draw_hz())

        ttk.Label(panel, text="SIZE VS. EARTH", style="Key.TLabel").pack(anchor="w", pady=(8, 2))
        self.size_canvas = tk.Canvas(panel, height=90, background=BG, highlightthickness=0)
        self.size_canvas.pack(fill="x")
        self.size_canvas.bind("<Configure>", lambda _: self._draw_size())

        return panel

    def _build_statusbar(self) -> None:
        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel",
                  padding=(14, 0, 14, 8)).pack(side="bottom", fill="x")

    # ---- data loading -------------------------------------------------------------------------

    def load(self, force_refresh: bool) -> None:
        self.refresh_button.configure(state="disabled")
        self.status_var.set("Fetching planets from the NASA Exoplanet Archive…")

        def worker():
            try:
                rows, source = api.load_planets(force_refresh)
                self._results.put(([Planet.from_row(r) for r in rows], source))
            except Exception as exc:  # reported in the status bar
                self._results.put(exc)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_results)

    def _poll_results(self) -> None:
        try:
            result = self._results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_results)
            return
        self.refresh_button.configure(state="normal")
        if isinstance(result, Exception):
            self.status_var.set(f"Could not load data: {result}")
            return
        self.planets, self.source = result
        methods = sorted({p.method for p in self.planets if p.method})
        self.method_box.configure(values=["Any method", *methods])
        self.refresh_table()

    # ---- table --------------------------------------------------------------------------------

    def _filtered(self) -> list[Planet]:
        text = self.search_var.get().strip().lower()
        zone_filter = self.zone_var.get()
        method = self.method_var.get()
        result = []
        for p in self.planets:
            if zone_filter == FILTER_HZ and not p.in_habitable_zone:
                continue
            if zone_filter == FILTER_CONSERVATIVE and p.zone != ZONE_CONSERVATIVE:
                continue
            if method != "Any method" and p.method != method:
                continue
            if self.rocky_var.get() and (p.radius is None or p.radius > 1.6):
                continue
            if text and text not in p.name.lower() and text not in p.host.lower():
                continue
            result.append(p)
        return result

    def sort_by(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = column in ("esi", "year")
        self.refresh_table()

    def refresh_table(self) -> None:
        getter = next(c[4] for c in COLUMNS if c[0] == self.sort_column)
        planets = self._filtered()
        known = [p for p in planets if getter(p) is not None]
        unknown = [p for p in planets if getter(p) is None]
        known.sort(key=lambda p: (getter(p).lower() if isinstance(getter(p), str) else getter(p)),
                   reverse=self.sort_descending)
        planets = known + unknown  # missing values always last

        for col_id, heading, *_ in COLUMNS:
            arrow = (" ▼" if self.sort_descending else " ▲") if col_id == self.sort_column else ""
            self.tree.heading(col_id, text=heading + arrow)

        self.tree.delete(*self.tree.get_children())
        self.by_iid.clear()
        for p in planets:
            values = [fmt(getter_(p), formatter, ESTIMATED_FIELD.get(col_id) in p.estimated)
                      for col_id, _, _, _, getter_, formatter in COLUMNS]
            iid = self.tree.insert("", "end", values=values, tags=(p.zone,))
            self.by_iid[iid] = p
            if p is self.selected:
                self.tree.selection_set(iid)
                self.tree.see(iid)

        if self.planets:
            habitable = sum(p.in_habitable_zone for p in self.planets)
            self.status_var.set(
                f"Showing {len(planets)} planets · {habitable} of {len(self.planets)} small planets "
                f"lie in the habitable zone · data {self.source} · values marked ~ are estimated")

    # ---- detail panel -------------------------------------------------------------------------

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected = self.by_iid[selection[0]]
        self._show_detail(self.selected)

    def _show_detail(self, p: Planet) -> None:
        est = p.estimated
        self.title_label.configure(text=p.name)
        self.subtitle_label.configure(
            text=f"Orbits {p.host}" + (f" ({p.spectype})" if p.spectype else "")
            + (f" · {p.distance_ly:,.1f} light-years away" if p.distance_ly else ""))

        values = {
            "zone": p.zone,
            "esi": fmt(p.esi, "{:.2f}".format, bool(est & {"radius", "insolation"})),
            "size": p.size_class,
            "radius": fmt(p.radius, "{:.2f} R⊕".format, "radius" in est),
            "mass": fmt(p.mass, "{:.2f} M⊕".format)
            + (" (est.)" if p.mass_provenance and "Mass" not in p.mass_provenance else ""),
            "insol": fmt(p.insolation, "{:.2f} S⊕".format, "insolation" in est),
            "teq": fmt(p.eq_temp, lambda t: f"{t:.0f} K ({t - 273.15:+.0f} °C)", "eq_temp" in est),
            "period": fmt(p.period, "{:,.2f} days".format),
            "sma": fmt(p.semi_major_axis, "{:.4f} AU".format, "semi_major_axis" in est),
            "ecc": fmt(p.eccentricity, "{:.3f}".format),
            "star": fmt(p.teff, "{:,.0f} K".format)
            + (f", {p.st_radius:.2f} R☉" if p.st_radius else "")
            + (f", {p.st_mass:.2f} M☉" if p.st_mass else ""),
            "lum": fmt(p.luminosity, "{:.4g} L☉".format, "luminosity" in est),
            "dist": fmt(p.distance_pc, lambda d: f"{d:,.2f} pc ({d * 3.26156:,.1f} ly)"),
            "system": f"{p.star_count or '?'} star(s), {p.planet_count or '?'} planet(s)",
            "disc": f"{p.disc_year or '?'} · {p.method or 'unknown method'}",
            "coords": fmt(p.ra, "{:.3f}°".format) + " / " + fmt(p.dec, "{:+.3f}°".format),
        }
        for key, text in values.items():
            self.detail_values[key].configure(text=text)
        self.detail_values["zone"].configure(foreground=ZONE_COLORS.get(p.zone, FG))

        notes = []
        if p.facility:
            notes.append(f"Discovered by {p.facility}.")
        if est:
            notes.append("Values marked ~ are derived from other parameters, not measured.")
        if p.mass_provenance and "Mass" not in p.mass_provenance:
            notes.append(f"Mass is a {p.mass_provenance.lower()} value.")
        self.note_label.configure(text=" ".join(notes))
        self.archive_button.configure(state="normal")
        self._draw_hz()
        self._draw_size()

    def _open_archive(self) -> None:
        if self.selected:
            webbrowser.open(api.overview_url(self.selected.name))

    def _draw_hz(self) -> None:
        c = self.hz_canvas
        c.delete("all")
        p = self.selected
        width, height = c.winfo_width(), c.winfo_height()
        if p is None:
            return
        if p.hz is None or p.semi_major_axis is None:
            c.create_text(width / 2, height / 2, text="Not enough data to place this orbit", fill=MUTED)
            return
        d = p.hz.distance
        a = p.semi_major_axis
        x0, mid = 24, height / 2 - 2
        scale = (width - 2 * x0) / (max(d["early_mars"], a) * 1.12)

        def x(au):
            return x0 + au * scale

        c.create_rectangle(x(d["recent_venus"]), mid - 26, x(d["early_mars"]), mid + 26,
                           fill=HZ_OPTIMISTIC_FILL, width=0)
        c.create_rectangle(x(d["runaway_greenhouse"]), mid - 26, x(d["maximum_greenhouse"]), mid + 26,
                           fill=HZ_CONSERVATIVE_FILL, width=0)
        c.create_line(x0, mid, width - x0 / 2, mid, fill=BORDER, dash=(2, 3))
        c.create_oval(x0 - 9, mid - 9, x0 + 9, mid + 9, fill=star_color(p.teff), outline="")
        color = ZONE_COLORS.get(p.zone, FG)
        c.create_oval(x(a) - 6, mid - 6, x(a) + 6, mid + 6, fill=color, outline=FG)
        c.create_text(x(a), mid - 37, text=p.name, fill=color, font=("Segoe UI", 9, "bold"))
        c.create_text(x(a), mid + 36, text=f"{a:.3g} AU", fill=FG, font=("Segoe UI", 8))
        c.create_text((x(d["runaway_greenhouse"]) + x(d["maximum_greenhouse"])) / 2, height - 6,
                      text=f"conservative HZ {d['runaway_greenhouse']:.3g}–{d['maximum_greenhouse']:.3g} AU",
                      fill=MUTED, font=("Segoe UI", 8))

    def _draw_size(self) -> None:
        c = self.size_canvas
        c.delete("all")
        p = self.selected
        width, height = c.winfo_width(), c.winfo_height()
        if p is None:
            return
        if p.radius is None:
            c.create_text(width / 2, height / 2, text="Radius unknown", fill=MUTED)
            return
        unit = (height - 30) / 2 / max(p.radius, 1.0)  # pixels per Earth radius
        cy = (height - 18) / 2
        ex, px = width * 0.3, width * 0.65
        c.create_oval(ex - unit, cy - unit, ex + unit, cy + unit, fill=EARTH, outline="")
        c.create_text(ex, height - 8, text="Earth (1.00 R⊕)", fill=MUTED, font=("Segoe UI", 8))
        r = p.radius * unit
        color = ZONE_COLORS.get(p.zone, FG)
        c.create_oval(px - r, cy - r, px + r, cy + r, fill=color, outline="")
        c.create_text(px, height - 8, text=f"{p.name} ({'~' if 'radius' in p.estimated else ''}"
                                           f"{p.radius:.2f} R⊕)", fill=MUTED, font=("Segoe UI", 8))


def main() -> None:
    TerraBrowser().mainloop()
