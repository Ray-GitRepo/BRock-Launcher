#!/usr/bin/env python3
"""
BRock Installer — Beta-1.0.0
Standalone dependency installer for BRock Launcher.
"""

import gi, subprocess, threading, os
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk, GdkPixbuf

HERE       = os.environ.get("APPDIR", os.path.dirname(os.path.abspath(__file__)))
ASSETS     = os.path.join(HERE, "assets")
ICON       = os.path.join(ASSETS, "icons", "icon.png")
FLATPAK_ID = "io.mrarm.mcpelauncher"
APP_VER    = "Beta-1.1"

CSS = """
* { font-family: 'Inter', 'Segoe UI', 'Ubuntu', 'Noto Sans', sans-serif; outline: none; -gtk-outline-radius: 0; }
window, .background { background-color: #0d1117; color: #e6edf3; }
button:focus { outline: none; box-shadow: none; }

/* ── HEADER ── */
.header-bar {
    background-color: #090d13;
    border-bottom: 1px solid #21262d;
    padding: 20px 28px 16px 28px;
}
.app-title {
    font-size: 20px; font-weight: 800;
    color: #e6edf3; letter-spacing: -0.02em;
}
.app-sub { font-size: 12px; color: #484f58; }

/* ── SECTION LABELS ── */
.section-lbl {
    font-size: 10px; font-weight: 700;
    color: #484f58; letter-spacing: 0.12em;
    margin-top: 16px; margin-bottom: 6px;
}

/* ── STEP CARDS ── */
.step-card {
    background-color: #111720;
    border: 1px solid #1e2530;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 6px;
}
.step-card-active {
    background: linear-gradient(135deg, #0d2118 0%, #0d1a14 100%);
    border-color: #3fcf8e;
}
.step-card-done  { background-color: #0a1a10; border-color: #238636; }
.step-card-error { background-color: #1a0c0c; border-color: #f85149; }

/* ── STEP NUMBER CIRCLE ── */
.step-circle {
    background-color: #1c2330;
    border: 1px solid #2a3344;
    border-radius: 20px;
    min-width: 36px; min-height: 36px;
    font-size: 13px; font-weight: 800;
    color: #3d4a5c;
}
.step-circle-active { background-color: rgba(63,207,142,0.15); border: 2px solid #3fcf8e; color: #3fcf8e; }
.step-circle-done   { background-color: rgba(35,134,54,0.20);  border: 2px solid #2ea043; color: #3fcf8e; }
.step-circle-error  { background-color: rgba(248,81,73,0.15);  border: 2px solid #f85149; color: #f85149; }

/* ── STEP TEXT ── */
.step-name         { font-size: 14px; font-weight: 700; color: #c9d1d9; }
.step-name-active  { color: #e6edf3; }
.step-name-done    { color: #7ee787; }
.step-desc         { font-size: 11px; color: #3d4a5c; margin-top: 1px; }
.step-desc-active  { color: #484f58; }

/* ── BADGES ── */
.badge {
    border-radius: 5px; padding: 3px 9px;
    font-size: 10px; font-weight: 800; letter-spacing: 0.08em;
}
.badge-pending { background-color: #161d28; border: 1px solid #2a3344;               color: #3d4a5c; }
.badge-active  { background-color: rgba(63,207,142,0.12); border: 1px solid #3fcf8e; color: #3fcf8e; }
.badge-done    { background-color: rgba(46,160,67,0.15);  border: 1px solid #2ea043; color: #7ee787; }
.badge-error   { background-color: rgba(248,81,73,0.12);  border: 1px solid #f85149; color: #f85149; }

/* ── PROGRESS ── */
progressbar trough   { background-color: #161d28; border-radius: 3px; min-height: 5px; border: none; }
progressbar progress { background-color: #3fcf8e; border-radius: 3px; min-height: 5px; border: none; }

/* ── CONSOLE ── */
.console {
    background-color: #080c10; color: #3fcf8e;
    font-family: 'JetBrains Mono','Fira Code','Cascadia Code','Consolas',monospace;
    font-size: 11px; padding: 12px;
    border: 1px solid #1e2530; border-radius: 8px;
}
textview.console text { background-color: #080c10; color: #3fcf8e; }

/* ── BUTTONS ── */
.btn-install {
    background-color: #238636; color: #ffffff;
    font-size: 13px; font-weight: 700; letter-spacing: 0.04em;
    border-radius: 9px; border: 1px solid rgba(63,207,142,0.25);
    padding: 0 28px; min-height: 40px;
}
.btn-install:hover    { background-color: #2ea043; }
.btn-install:active   { opacity: 0.85; }
.btn-install:disabled { background-color: #1c2330; color: #3d4a5c; border-color: #1c2330; }

.btn-cancel {
    background-color: transparent; color: #484f58;
    border: 1px solid #1e2530; border-radius: 9px;
    font-size: 13px; font-weight: 600;
    padding: 0 20px; min-height: 40px;
}
.btn-cancel:hover    { background-color: #111720; color: #8b949e; border-color: #2a3344; }
.btn-cancel:disabled { opacity: 0.40; }

/* ── STATUS ── */
.status-text { font-size: 12px; color: #484f58; }

/* ── SUCCESS ── */
.success-big    { font-size: 52px; font-weight: 900; color: #3fcf8e; letter-spacing: -0.04em; }
.success-title  { font-size: 22px; font-weight: 800; color: #e6edf3; letter-spacing: -0.02em; }
.success-sub    { font-size: 13px; color: #484f58; }
.success-card   {
    background-color: #0a1a10;
    border: 1px solid #1f3d28;
    border-radius: 10px; padding: 18px 22px;
}
.success-line   { font-size: 13px; font-weight: 600; color: #7ee787; }

/* ── MISC ── */
separator { background-color: #1e2530; min-height: 1px; }
.version-id { font-size: 11px; color: #3d4a5c; }
scrollbar { background-color: transparent; border: none; }
scrollbar slider { background-color: #1e2530; border-radius: 4px; min-width: 5px; min-height: 24px; margin: 2px; }
scrollbar slider:hover  { background-color: #2a3344; }
scrollbar slider:active { background-color: #3fcf8e; }
"""

def _run(*cmd):
    try:    return subprocess.run(list(cmd), capture_output=True, text=True)
    except: return None

def has_flatpak():
    r = _run("flatpak", "--version")
    return r is not None and r.returncode == 0

def has_mcpe():
    r = _run("flatpak", "info", FLATPAK_ID)
    return r is not None and r.returncode == 0

def mcpe_update_available():
    try:
        inst   = _run("flatpak", "info", "--show-commit", FLATPAK_ID)
        remote = _run("flatpak", "remote-info", "flathub", FLATPAK_ID)
        if not inst or not remote: return False
        ic = inst.stdout.strip()
        rc = [l for l in remote.stdout.splitlines() if "Commit:" in l]
        return bool(rc and ic and ic not in rc[0])
    except: return False

def apply_css():
    p = Gtk.CssProvider()
    p.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

def make_clickable(w):
    def _in(ww, _):
        try:
            win = ww.get_window()
            if win: win.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "pointer"))
        except: pass
    def _out(ww, _):
        try:
            win = ww.get_window()
            if win: win.set_cursor(None)
        except: pass
    w.connect("enter-notify-event", _in)
    w.connect("leave-notify-event", _out)

def apply_inline_css(widget, css):
    p = Gtk.CssProvider()
    p.load_from_data(css.encode())
    widget.get_style_context().add_provider(p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class BRockInstaller(Gtk.Window):
    ST_IDLE       = "idle"
    ST_CHECKING   = "checking"
    ST_INSTALLING = "installing"

    def __init__(self):
        super().__init__(title=f"BRock Installer")
        self.set_default_size(500, 560)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", Gtk.main_quit)
        if os.path.exists(ICON):
            try: self.set_icon_from_file(ICON)
            except: pass
        apply_css()
        self._state   = self.ST_IDLE
        self._steps   = []
        self._pulsing = False
        self._build()
        self.show_all()
        GLib.idle_add(self._do_check)

    # ── BUILD ──────────────────────────────────────────────────────────────

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        self._root = root

        # Header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        hdr.get_style_context().add_class("header-bar")

        # Icon
        if os.path.exists(ICON):
            try:
                pb  = GdkPixbuf.Pixbuf.new_from_file_at_scale(ICON, 42, 42, True)
                img = Gtk.Image.new_from_pixbuf(pb)
                img.set_valign(Gtk.Align.CENTER)
                hdr.pack_start(img, False, False, 0)
            except: pass

        title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title_col.set_valign(Gtk.Align.CENTER)
        tl = Gtk.Label(label="BRock Installer", xalign=0)
        tl.get_style_context().add_class("app-title")
        sl = Gtk.Label(label="Dependency setup for BRock Launcher", xalign=0)
        sl.get_style_context().add_class("app-sub")
        title_col.pack_start(tl, False, False, 0)
        title_col.pack_start(sl, False, False, 0)
        hdr.pack_start(title_col, True, True, 0)

        # Version badge in header
        ver_lbl = Gtk.Label(label=APP_VER)
        apply_inline_css(ver_lbl,
            "label { background-color: #161d28; border: 1px solid #2a3344; "
            "border-radius: 5px; padding: 4px 10px; font-size: 10px; "
            "font-weight: 700; color: #e5fdef; letter-spacing: 0.06em; }")
        ver_lbl.set_valign(Gtk.Align.CENTER)
        hdr.pack_start(ver_lbl, False, False, 0)

        root.pack_start(hdr, False, False, 0)
        root.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # Scrollable content
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_margin_start(22); content.set_margin_end(22)
        content.set_margin_top(4);    content.set_margin_bottom(16)
        sw.add(content)
        root.pack_start(sw, True, True, 0)

        sec = Gtk.Label(label="SYSTEM CHECKS", xalign=0)
        sec.get_style_context().add_class("section-lbl")
        content.pack_start(sec, False, False, 0)

        self._cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.pack_start(self._cards_box, False, False, 0)

        # Progress
        self._pbar = Gtk.ProgressBar()
        self._pbar.set_margin_top(14); self._pbar.set_margin_bottom(4)
        self._pbar.set_no_show_all(True)
        content.pack_start(self._pbar, False, False, 0)

        # Log
        log_sec = Gtk.Label(label="OUTPUT", xalign=0)
        log_sec.get_style_context().add_class("section-lbl")
        log_sec.set_no_show_all(True)
        self._log_sec = log_sec
        content.pack_start(log_sec, False, False, 0)

        self._log_sw = Gtk.ScrolledWindow()
        self._log_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._log_sw.set_size_request(-1, 130)
        self._log_sw.set_margin_top(4)
        self._log_sw.set_no_show_all(True)
        self._log_tv  = Gtk.TextView()
        self._log_tv.set_editable(False)
        self._log_tv.set_monospace(True)
        self._log_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_tv.get_style_context().add_class("console")
        self._log_buf = self._log_tv.get_buffer()
        self._log_sw.add(self._log_tv)
        content.pack_start(self._log_sw, False, False, 0)

        # Bottom bar
        root.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom.set_margin_start(22); bottom.set_margin_end(22)
        bottom.set_margin_top(14);   bottom.set_margin_bottom(14)

        self._status_lbl = Gtk.Label(label="Checking your system…", xalign=0)
        self._status_lbl.get_style_context().add_class("status-text")
        self._status_lbl.set_hexpand(True)
        bottom.pack_start(self._status_lbl, True, True, 0)

        self._cancel_btn = Gtk.Button(label="Cancel")
        self._cancel_btn.get_style_context().add_class("btn-cancel")
        self._cancel_btn.set_size_request(90, 40)
        self._cancel_btn.connect("clicked", lambda *_: Gtk.main_quit())
        make_clickable(self._cancel_btn)
        bottom.pack_start(self._cancel_btn, False, False, 0)

        self._action_btn = Gtk.Button(label="Checking…")
        self._action_btn.get_style_context().add_class("btn-install")
        self._action_btn.set_size_request(150, 40)
        self._action_btn.set_sensitive(False)
        self._action_btn.connect("clicked", self._on_action)
        make_clickable(self._action_btn)
        bottom.pack_start(self._action_btn, False, False, 0)

        root.pack_start(bottom, False, False, 0)

    # ── STEP CARDS ─────────────────────────────────────────────────────────

    def _add_step_card(self, number, name, desc):
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.get_style_context().add_class("step-card")
        card.set_margin_top(0)

        # Number circle
        circle = Gtk.Box()
        circle.set_size_request(36, 36)
        circle.set_halign(Gtk.Align.CENTER)
        circle.set_valign(Gtk.Align.CENTER)
        circle.get_style_context().add_class("step-circle")
        num_lbl = Gtk.Label(label=str(number))
        num_lbl.set_halign(Gtk.Align.CENTER)
        num_lbl.set_valign(Gtk.Align.CENTER)
        circle.pack_start(num_lbl, True, True, 0)

        # Text block
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        text.set_hexpand(True)
        text.set_valign(Gtk.Align.CENTER)
        name_lbl = Gtk.Label(label=name, xalign=0)
        name_lbl.get_style_context().add_class("step-name")
        desc_lbl = Gtk.Label(label=desc, xalign=0)
        desc_lbl.get_style_context().add_class("step-desc")
        desc_lbl.set_line_wrap(True)
        text.pack_start(name_lbl, False, False, 0)
        text.pack_start(desc_lbl, False, False, 0)

        # Badge
        badge = Gtk.Label(label="PENDING")
        badge.get_style_context().add_class("badge")
        badge.get_style_context().add_class("badge-pending")
        badge.set_valign(Gtk.Align.CENTER)

        card.pack_start(circle, False, False, 0)
        card.pack_start(text,   True,  True,  0)
        card.pack_start(badge,  False, False, 0)
        self._cards_box.pack_start(card, False, False, 0)
        card.show_all()
        return card, circle, badge, name_lbl, desc_lbl

    def _set_card_state(self, card, circle, badge, name_lbl, desc_lbl, state):
        for cls in ("step-card-active","step-card-done","step-card-error"):
            card.get_style_context().remove_class(cls)
        for cls in ("step-circle-active","step-circle-done","step-circle-error"):
            circle.get_style_context().remove_class(cls)
        for cls in ("badge-pending","badge-active","badge-done","badge-error"):
            badge.get_style_context().remove_class(cls)
        for cls in ("step-name-active","step-name-done"):
            name_lbl.get_style_context().remove_class(cls)
        for cls in ("step-desc-active",):
            desc_lbl.get_style_context().remove_class(cls)

        if state == "active":
            card.get_style_context().add_class("step-card-active")
            circle.get_style_context().add_class("step-circle-active")
            badge.set_text("RUNNING"); badge.get_style_context().add_class("badge-active")
            name_lbl.get_style_context().add_class("step-name-active")
            desc_lbl.get_style_context().add_class("step-desc-active")
        elif state == "done":
            card.get_style_context().add_class("step-card-done")
            circle.get_style_context().add_class("step-circle-done")
            badge.set_text("DONE"); badge.get_style_context().add_class("badge-done")
            name_lbl.get_style_context().add_class("step-name-done")
        elif state == "error":
            card.get_style_context().add_class("step-card-error")
            circle.get_style_context().add_class("step-circle-error")
            badge.set_text("FAILED"); badge.get_style_context().add_class("badge-error")
        else:
            badge.set_text("PENDING"); badge.get_style_context().add_class("badge-pending")

    # ── LOG ────────────────────────────────────────────────────────────────

    def _log(self, line):
        it = self._log_buf.get_end_iter()
        self._log_buf.insert(it, line + "\n")
        GLib.idle_add(lambda: self._log_sw.get_vadjustment().set_value(
            self._log_sw.get_vadjustment().get_upper()))

    # ── CHECK ──────────────────────────────────────────────────────────────

    def _do_check(self):
        self._state = self.ST_CHECKING
        def _work():
            fp  = has_flatpak()
            mc  = has_mcpe() if fp else False
            upd = mcpe_update_available() if mc else False
            def _update():
                for c in list(self._cards_box.get_children()):
                    self._cards_box.remove(c)
                self._steps = []
                step = 1

                if not fp:
                    card, circle, badge, nl, dl = self._add_step_card(
                        step, "Install Flatpak", "Required package manager — not installed")
                    self._steps.append({"type":"flatpak","action":"install",
                        "card":card,"circle":circle,"badge":badge,"nl":nl,"dl":dl})
                    step += 1

                if not fp or not mc:
                    card, circle, badge, nl, dl = self._add_step_card(
                        step, "Add Flathub", "App store source for mcpelauncher")
                    self._steps.append({"type":"flathub","action":"add",
                        "card":card,"circle":circle,"badge":badge,"nl":nl,"dl":dl})
                    step += 1

                if not mc:
                    card, circle, badge, nl, dl = self._add_step_card(
                        step, "Install mcpelauncher",
                        f"{FLATPAK_ID}")
                    self._steps.append({"type":"mcpe","action":"install",
                        "card":card,"circle":circle,"badge":badge,"nl":nl,"dl":dl})
                elif upd:
                    card, circle, badge, nl, dl = self._add_step_card(
                        step, "Update mcpelauncher", "Newer version available on Flathub")
                    self._steps.append({"type":"mcpe","action":"update",
                        "card":card,"circle":circle,"badge":badge,"nl":nl,"dl":dl})

                if not self._steps:
                    self._status_lbl.set_text("Everything is installed and up to date.")
                    self._action_btn.set_label("Close")
                    self._action_btn.set_sensitive(True)
                    self._state = "close"

                    # Show an "all good" card
                    ok_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
                    ok_card.get_style_context().add_class("step-card")
                    ok_card.get_style_context().add_class("step-card-done")
                    ok_card.set_margin_top(0)
                    tick = Gtk.Label()
                    tick.set_markup("<span color='#3fcf8e' size='x-large' weight='bold'>✓</span>")
                    tick.set_valign(Gtk.Align.CENTER)
                    lbl = Gtk.Label(label="All dependencies are already installed", xalign=0)
                    lbl.get_style_context().add_class("step-name")
                    lbl.get_style_context().add_class("step-name-done")
                    ok_card.pack_start(tick, False, False, 0)
                    ok_card.pack_start(lbl,  True,  True,  0)
                    self._cards_box.pack_start(ok_card, False, False, 0)
                else:
                    n = len(self._steps)
                    self._status_lbl.set_text(
                        f"{n} item{'s' if n>1 else ''} to install.")
                    self._action_btn.set_label("▶  Install")
                    self._action_btn.set_sensitive(True)
                    self._state = self.ST_IDLE

                self._root.show_all()
            GLib.idle_add(_update)
        threading.Thread(target=_work, daemon=True).start()

    # ── INSTALL ────────────────────────────────────────────────────────────

    def _on_action(self, *_):
        if self._state == "close": Gtk.main_quit(); return
        if self._state != self.ST_IDLE: return
        self._state = self.ST_INSTALLING
        self._action_btn.set_sensitive(False)
        self._cancel_btn.set_sensitive(False)
        self._pbar.show(); self._log_sec.show(); self._log_sw.show()
        self._pbar.set_pulse_step(0.03)
        self._pulsing = True
        def _pulse():
            if self._pulsing: self._pbar.pulse(); return True
            return False
        GLib.timeout_add(55, _pulse)
        threading.Thread(target=self._run_steps, daemon=True).start()

    def _run_steps(self):
        total = len(self._steps); errors = []
        for i, step in enumerate(self._steps):
            t = step["type"]; act = step["action"]
            card = step["card"]; circle = step["circle"]
            badge = step["badge"]; nl = step["nl"]; dl = step["dl"]
            GLib.idle_add(self._set_card_state, card, circle, badge, nl, dl, "active")
            GLib.idle_add(self._status_lbl.set_text, f"Step {i+1} of {total}…")
            ok = False

            if t == "flatpak":
                GLib.idle_add(self._log, "→ Installing Flatpak via apt…")
                try:
                    proc = subprocess.Popen(
                        ["pkexec","apt-get","install","-y","flatpak"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in iter(proc.stdout.readline,""):
                        if line.strip(): GLib.idle_add(self._log, line.rstrip())
                    proc.wait(); ok = proc.returncode == 0
                    GLib.idle_add(self._log, "✓ Flatpak installed." if ok else "✕ apt-get failed.")
                except FileNotFoundError:
                    GLib.idle_add(self._log, "✕ pkexec not found — try: sudo apt install flatpak")
                except Exception as e:
                    GLib.idle_add(self._log, f"✕ {e}")

            elif t == "flathub":
                GLib.idle_add(self._log, "→ Adding Flathub remote…")
                try:
                    r = subprocess.run(
                        ["flatpak","remote-add","--if-not-exists","flathub",
                         "https://dl.flathub.org/repo/flathub.flatpakrepo"],
                        capture_output=True, text=True)
                    ok = r.returncode == 0
                    GLib.idle_add(self._log,
                        "✓ Flathub added." if ok else f"✕ {r.stderr.strip()}")
                except Exception as e:
                    GLib.idle_add(self._log, f"✕ {e}")

            elif t == "mcpe":
                verb = "update" if act == "update" else "install"
                GLib.idle_add(self._log, f"→ flatpak {verb} {FLATPAK_ID} --no-related…")
                try:
                    proc = subprocess.Popen(
                        ["flatpak",verb,"flathub",FLATPAK_ID,"--no-related","-y"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in iter(proc.stdout.readline,""):
                        if line.strip(): GLib.idle_add(self._log, line.rstrip())
                    proc.wait(); ok = proc.returncode == 0
                    GLib.idle_add(self._log,
                        "✓ mcpelauncher ready." if ok else "✕ Install failed.")
                except Exception as e:
                    GLib.idle_add(self._log, f"✕ {e}")

            GLib.idle_add(self._set_card_state, card, circle, badge, nl, dl,
                          "done" if ok else "error")
            if not ok: errors.append(t)

        self._pulsing = False
        def _finish():
            self._pbar.set_fraction(1.0)
            if not errors: self._show_success()
            else:
                self._state = "close"
                self._status_lbl.set_text(f"Failed: {', '.join(errors)}. See output above.")
                self._action_btn.set_label("Close")
                self._action_btn.set_sensitive(True)
        GLib.idle_add(_finish)

    # ── SUCCESS ────────────────────────────────────────────────────────────

    def _show_success(self):
        self.remove(self._root)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        # Same header
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        hdr.get_style_context().add_class("header-bar")
        if os.path.exists(ICON):
            try:
                pb  = GdkPixbuf.Pixbuf.new_from_file_at_scale(ICON, 42, 42, True)
                img = Gtk.Image.new_from_pixbuf(pb)
                img.set_valign(Gtk.Align.CENTER)
                hdr.pack_start(img, False, False, 0)
            except: pass
        tc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        tc.set_valign(Gtk.Align.CENTER)
        tl = Gtk.Label(label="BRock Installer", xalign=0)
        tl.get_style_context().add_class("app-title")
        sl = Gtk.Label(label="Setup complete", xalign=0)
        sl.get_style_context().add_class("app-sub")
        tc.pack_start(tl, False, False, 0)
        tc.pack_start(sl, False, False, 0)
        hdr.pack_start(tc, True, True, 0)
        root.pack_start(hdr, False, False, 0)
        root.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # Body
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        body.set_margin_start(28); body.set_margin_end(28)
        body.set_margin_top(28);   body.set_margin_bottom(14)
        body.set_vexpand(True)

        # Big tick area
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        center.set_vexpand(True)

        tick = Gtk.Label()
        tick.set_markup("<span color='#3fcf8e' weight='ultrabold'>✓</span>")
        tick.get_style_context().add_class("success-big")
        tick.set_halign(Gtk.Align.CENTER)
        center.pack_start(tick, False, False, 0)

        done_lbl = Gtk.Label(label="All done!", xalign=0.5)
        done_lbl.get_style_context().add_class("success-title")
        done_lbl.set_halign(Gtk.Align.CENTER)
        done_lbl.set_margin_top(4)
        center.pack_start(done_lbl, False, False, 0)

        sub = Gtk.Label(
            label="Your system is ready.\nYou can now run BRock Launcher.",
            xalign=0.5)
        sub.get_style_context().add_class("success-sub")
        sub.set_halign(Gtk.Align.CENTER)
        sub.set_justify(Gtk.Justification.CENTER)
        sub.set_margin_top(6)
        center.pack_start(sub, False, False, 0)

        body.pack_start(center, True, True, 0)

        # Summary card
        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        summary.get_style_context().add_class("success-card")
        summary.set_margin_top(20)

        sec_lbl = Gtk.Label(label="INSTALLED", xalign=0)
        sec_lbl.get_style_context().add_class("section-lbl")
        sec_lbl.set_margin_top(0)
        summary.pack_start(sec_lbl, False, False, 0)

        for line in (
            "✓  Flatpak",
            "✓  Flathub remote",
            f"✓  {FLATPAK_ID}",
        ):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            l = Gtk.Label(label=line, xalign=0)
            l.get_style_context().add_class("success-line")
            row.pack_start(l, True, True, 0)
            summary.pack_start(row, False, False, 0)

        body.pack_start(summary, False, False, 0)
        root.pack_start(body, True, True, 0)

        # Bottom
        root.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom.set_margin_start(22); bottom.set_margin_end(22)
        bottom.set_margin_top(14);   bottom.set_margin_bottom(14)
        bottom.pack_start(Gtk.Box(), True, True, 0)

        close_btn = Gtk.Button(label="Close")
        close_btn.get_style_context().add_class("btn-install")
        close_btn.set_size_request(150, 40)
        close_btn.connect("clicked", lambda *_: Gtk.main_quit())
        make_clickable(close_btn)
        bottom.pack_start(close_btn, False, False, 0)
        root.pack_start(bottom, False, False, 0)

        root.show_all()


if __name__ == "__main__":
    win = BRockInstaller()
    win.show_all()
    Gtk.main()