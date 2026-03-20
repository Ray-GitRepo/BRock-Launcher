#!/usr/bin/env python3

import gi, os, subprocess, zipfile, json, struct, math, cairo
import threading, shutil, sys, time, random

os.environ.setdefault("G_MESSAGES_DEBUG", "")
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

LAUNCHER_VERSION       = "Beta-1.1"
PLAYTIME_FORMAT        = "hm"
QUICK_LAUNCH_COUNT     = 5
NOTIF_AUTODISMISS_SECS = 8

BASE       = os.path.dirname(os.path.abspath(__file__))
ASSETS     = os.path.join(BASE, "assets")
CONFIG_DIR = os.path.expanduser("~/.config/mc-launcher")
GAME           = os.path.expanduser("~/mcpe_game")
GAME_DIR       = os.path.join(GAME, "Version")
SERVER_DIR     = os.path.join(GAME, "Servers")
THEME_DIR      = os.path.join(GAME, "Assets", "themes")
BG_DIR         = os.path.join(GAME, "Assets", "backgrounds")
COM_MOJANG_DIR = os.path.join(GAME, "Storage/games/com.mojang")
COM_MOJANG     = Path(GAME, "Storage")
NOTIFY_FILE    = os.path.join(CONFIG_DIR, "cache",  "notify.json")
SETTINGS_FILE  = os.path.join(CONFIG_DIR, "data",   "settings.json")
PROFILE_FILE   = os.path.join(CONFIG_DIR, "user",   "profile.json")
PLAYTIME_FILE  = os.path.join(CONFIG_DIR, "user",   "playtime.json")
GAMELOG_FILE   = os.path.join(CONFIG_DIR, "cache",  "gamelog.txt")
CUSTOM_SKINS   = os.path.join(COM_MOJANG_DIR, "custom_skins")
BEHAVIOUR_DIR  = os.path.join(COM_MOJANG_DIR, "behavior_packs")
RESOURCE_DIR   = os.path.join(COM_MOJANG_DIR, "resource_packs")
WORLDS_DIR     = os.path.join(COM_MOJANG_DIR, "minecraftWorlds")
BG_DATA        = os.path.join(ASSETS, "backgrounds")
THEME_DATA     = os.path.join(ASSETS, "themes")
MOD_DIR        = os.path.join(BASE, "mods")

for src, dst in ((BG_DATA, BG_DIR), (THEME_DATA, THEME_DIR)):
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
for d in (GAME_DIR, SERVER_DIR, BG_DIR, COM_MOJANG_DIR, CONFIG_DIR, THEME_DIR,
          os.path.join(CONFIG_DIR,"cache"), os.path.join(CONFIG_DIR,"data"),
          os.path.join(CONFIG_DIR,"user"),
          CUSTOM_SKINS, BEHAVIOUR_DIR, RESOURCE_DIR, WORLDS_DIR):
    os.makedirs(d, exist_ok=True)

# ── Log severity helpers ──────────────────────────────────────────
LOG_COLORS = {
    "error":   "#f85149",
    "warn":    "#f0c000",
    "info":    "#8b949e",
    "trace":   "#484f58",
    "success": "#3fcf8e",
    "default": "#c9d1d9",
}

def classify_log_line(line):
    low = line.lower()
    if any(w in low for w in ("error","exception","fatal","failed","crash")): return "error"
    if any(w in low for w in ("warn","warning")): return "warn"
    if any(w in low for w in ("trace","linker","redirect")): return "trace"
    if any(w in low for w in ("launching","loaded","success","started")): return "success"
    return "info"

# ── JSON helpers ─────────────────────────────────────────────────
def load_json_file(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                d = json.load(f)
            if isinstance(d, type(default)):
                return d
        except Exception:
            pass
    return default

def save_json_file(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[warn] {path}: {e}", flush=True)
        return False

DEFAULT_SETTINGS = {
    "allow_beta": False, "default_version": None,
    "background": "crystal.png", "random_background": False,
    "auto_quit": True, "theme": "default.css",
    "show_notifications": True, "splash_screen": True,
}
DEFAULT_PROFILE = {
    "username": "Player", "profile_picture": None,
    "launches": 0,
}

SHORTCUT_ACTIONS = [
    ("home",     "Go to Home",             "<Control>h"),
    ("versions", "Go to Versions",         "<Control>v"),
    ("servers",  "Go to Servers",          "<Control>e"),
    ("storage",  "Go to Storage",          "<Control>s"),
    ("import",   "Go to Import",           "<Control>i"),
    ("settings", "Go to Settings",         "<Control>comma"),
    ("play",     "Play default version",   "<Control>p"),
    ("reload",   "Reload launcher",        "<Control>r"),
    ("help",     "Show shortcuts",         "<Control>slash"),
]
DEFAULT_SHORTCUTS = {action: key for action, _, key in SHORTCUT_ACTIONS}
SHORTCUTS_FILE = os.path.join(CONFIG_DIR, "data", "shortcuts.json")

def load_shortcuts():
    d = load_json_file(SHORTCUTS_FILE, {})
    s = dict(DEFAULT_SHORTCUTS)
    if isinstance(d, dict): s.update(d)
    return s

def save_shortcuts(s): save_json_file(SHORTCUTS_FILE, s)

def load_settings():
    d = load_json_file(SETTINGS_FILE, {})
    s = dict(DEFAULT_SETTINGS)
    if isinstance(d, dict): s.update(d)
    return s
def save_settings(s): save_json_file(SETTINGS_FILE, s)
def set_setting(k, v): s = load_settings(); s[k] = v; save_settings(s)
def load_profile():
    d = load_json_file(PROFILE_FILE, {})
    p = dict(DEFAULT_PROFILE)
    if isinstance(d, dict): p.update(d)
    return p
def save_profile(p):   save_json_file(PROFILE_FILE, p)
def load_playtime():   return load_json_file(PLAYTIME_FILE, {})
def save_playtime(pt): save_json_file(PLAYTIME_FILE, pt)

def _play_notif_sound(ntype):
    """Play a system notification sound using available tools."""
    sound_map = {
        "success": ["audio-volume-change", "complete", "bell"],
        "error":   ["dialog-error", "bell"],
        "info":    ["message-new-instant", "message"],
        "warning": ["dialog-warning", "bell"],
    }
    ids = sound_map.get(ntype, ["bell"])
    def _try():
        for sid in ids:
            try:
                subprocess.Popen(
                    ["canberra-gtk-play", f"--id={sid}", "--volume=-3"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return
            except FileNotFoundError:
                pass
        # fallback: paplay with freedesktop sounds
        for sid in ids:
            for ext in (".oga", ".ogg", ".wav"):
                path = f"/usr/share/sounds/freedesktop/stereo/{sid}{ext}"
                if os.path.exists(path):
                    try:
                        subprocess.Popen(["paplay", path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return
                    except FileNotFoundError:
                        pass
    threading.Thread(target=_try, daemon=True).start()

# ── Theme names → accent colours for sidebar art ────────────────
THEME_PALETTES = {
    "forest":    {"art": "forest",    "accent": (0.22, 0.65, 0.28)},
    "ocean":     {"art": "ocean",     "accent": (0.12, 0.55, 0.80)},
    "crystallic":{"art": "crystallic","accent": (0.54, 0.36, 0.96)},
    "sunset":    {"art": "sunset",    "accent": (0.95, 0.45, 0.15)},
    "midnight":  {"art": "midnight",  "accent": (0.36, 0.28, 0.92)},
    "neon":      {"art": "neon",      "accent": (0.10, 0.95, 0.55)},
    "sakura":    {"art": "sakura",    "accent": (0.95, 0.55, 0.70)},
    "void":      {"art": "void",      "accent": (0.60, 0.60, 0.60)},
    "default":   {"art": "none",      "accent": (0.25, 0.81, 0.56)},
}

class ThemeArtWidget(Gtk.DrawingArea):
    """Draws theme-specific decorative art in the sidebar."""
    def __init__(self, theme_name="default"):
        super().__init__()
        self._theme = theme_name.replace(".css", "").lower()
        self.set_size_request(72, 180)
        self.connect("draw", self._on_draw)

    def set_theme(self, theme_name):
        self._theme = theme_name.replace(".css", "").lower()
        self.queue_draw()

    def _on_draw(self, widget, cr):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        info = THEME_PALETTES.get(self._theme, THEME_PALETTES["default"])
        art  = info["art"]
        r, g, b = info["accent"]
        cr.set_operator(cairo.OPERATOR_OVER)

        if art == "forest":
            self._draw_tree(cr, w, h, r, g, b)
        elif art == "ocean":
            self._draw_waves(cr, w, h, r, g, b)
        elif art == "crystallic":
            self._draw_crystals(cr, w, h, r, g, b)
        elif art == "sunset":
            self._draw_sun(cr, w, h, r, g, b)
        elif art == "midnight":
            self._draw_stars(cr, w, h, r, g, b)
        elif art == "neon":
            self._draw_lightning(cr, w, h, r, g, b)
        elif art == "sakura":
            self._draw_petals(cr, w, h, r, g, b)
        elif art == "void":
            self._draw_void(cr, w, h, r, g, b)

    def _draw_tree(self, cr, w, h, r, g, b):
        cx = w / 2
        # trunk
        cr.set_source_rgba(0.4, 0.25, 0.12, 0.55)
        cr.rectangle(cx - 4, h * 0.65, 8, h * 0.35)
        cr.fill()
        # canopy layers
        for i, (cy, rad, alpha) in enumerate([(0.55, 22, 0.50),(0.42, 18, 0.42),(0.30, 14, 0.35)]):
            cr.set_source_rgba(r * 0.7, g * 0.85, b * 0.5, alpha)
            cr.arc(cx, h * cy, rad, 0, 2 * math.pi); cr.fill()

    def _draw_waves(self, cr, w, h, r, g, b):
        for i, (y_off, alpha) in enumerate([(0.25,0.35),(0.45,0.28),(0.65,0.22)]):
            cr.set_source_rgba(r, g, b, alpha)
            cr.move_to(0, h * y_off)
            for x in range(0, w + 8, 8):
                yw = h * y_off + math.sin(x * 0.18 + i * 1.2) * 8
                cr.line_to(x, yw)
            cr.line_to(w, h); cr.line_to(0, h); cr.close_path(); cr.fill()

    def _draw_crystals(self, cr, w, h, r, g, b):
        gems = [(w*0.3, h*0.25, 12, 0.50), (w*0.65, h*0.50, 9, 0.38), (w*0.25, h*0.70, 7, 0.28)]
        for cx, cy, size, alpha in gems:
            cr.set_source_rgba(r, g, b, alpha)
            cr.move_to(cx, cy - size)
            cr.line_to(cx + size * 0.6, cy)
            cr.line_to(cx, cy + size * 1.2)
            cr.line_to(cx - size * 0.6, cy)
            cr.close_path(); cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.15)
            cr.move_to(cx, cy - size); cr.line_to(cx + size * 0.6, cy)
            cr.line_to(cx, cy - size * 0.1); cr.close_path(); cr.fill()

    def _draw_sun(self, cr, w, h, r, g, b):
        cx, cy, rad = w / 2, h * 0.35, 16
        cr.set_source_rgba(r, g, b, 0.45)
        cr.arc(cx, cy, rad, 0, 2 * math.pi); cr.fill()
        for i in range(8):
            angle = i * math.pi / 4
            x1 = cx + (rad + 4) * math.cos(angle); y1 = cy + (rad + 4) * math.sin(angle)
            x2 = cx + (rad + 12) * math.cos(angle); y2 = cy + (rad + 12) * math.sin(angle)
            cr.set_source_rgba(r, g, b, 0.30)
            cr.set_line_width(2); cr.move_to(x1, y1); cr.line_to(x2, y2); cr.stroke()

    def _draw_stars(self, cr, w, h, r, g, b):
        stars = [(w*0.2,h*0.12,3,0.7),(w*0.7,h*0.20,2,0.5),(w*0.5,h*0.08,2,0.6),
                 (w*0.8,h*0.40,2,0.4),(w*0.15,h*0.55,1.5,0.5),(w*0.6,h*0.65,1,0.35)]
        for sx, sy, sr, alpha in stars:
            cr.set_source_rgba(r, g, b, alpha)
            cr.arc(sx, sy, sr, 0, 2 * math.pi); cr.fill()
        # crescent moon
        cr.set_source_rgba(r * 0.9, g * 0.9, b, 0.40)
        cr.arc(w * 0.55, h * 0.35, 10, 0, 2 * math.pi); cr.fill()
        cr.set_source_rgba(0.06, 0.07, 0.10, 1.0)
        cr.arc(w * 0.60, h * 0.33, 8, 0, 2 * math.pi); cr.fill()

    def _draw_lightning(self, cr, w, h, r, g, b):
        cx = w / 2
        pts = [(cx+4, h*0.05),(cx-4, h*0.42),(cx+6, h*0.42),(cx-6, h*0.90)]
        cr.set_source_rgba(r, g, b, 0.55)
        cr.set_line_width(3)
        cr.move_to(*pts[0])
        for pt in pts[1:]: cr.line_to(*pt)
        cr.stroke()
        cr.set_source_rgba(r, g, b, 0.20)
        cr.set_line_width(7)
        cr.move_to(*pts[0])
        for pt in pts[1:]: cr.line_to(*pt)
        cr.stroke()

    def _draw_petals(self, cr, w, h, r, g, b):
        petals = [(w*0.3,h*0.25),(w*0.6,h*0.15),(w*0.5,h*0.50),(w*0.25,h*0.60),(w*0.7,h*0.70)]
        for px, py in petals:
            for angle in range(0, 360, 72):
                rad_a = math.radians(angle)
                ex = px + 7 * math.cos(rad_a); ey = py + 7 * math.sin(rad_a)
                cr.set_source_rgba(r, g, b, 0.40)
                cr.arc(ex, ey, 5, 0, 2 * math.pi); cr.fill()
            cr.set_source_rgba(1.0, 0.95, 0.7, 0.50)
            cr.arc(px, py, 2.5, 0, 2 * math.pi); cr.fill()

    def _draw_void(self, cr, w, h, r, g, b):
        for i, (rad, alpha) in enumerate([(30,0.08),(20,0.10),(10,0.14)]):
            cr.set_source_rgba(r, g, b, alpha)
            cr.arc(w / 2, h * 0.40, rad, 0, 2 * math.pi); cr.fill()
        cr.set_source_rgba(r, g, b, 0.28)
        cr.arc(w / 2, h * 0.40, 3, 0, 2 * math.pi); cr.fill()


_icon_cache = {}
def load_icon_async(path, widget, w, h):
    key = (path, w, h)
    if key in _icon_cache:
        widget.set_from_pixbuf(_icon_cache[key]); return
    def _work():
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, True)
            _icon_cache[key] = pb
            GLib.idle_add(widget.set_from_pixbuf, pb)
        except Exception: pass
    threading.Thread(target=_work, daemon=True).start()

def make_clickable(w):
    def _in(ww, _):
        try:
            win = ww.get_window()
            if win: win.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "pointer"))
        except Exception: pass
    def _out(ww, _):
        try:
            win = ww.get_window()
            if win: win.set_cursor(None)
        except Exception: pass
    w.connect("enter-notify-event", _in)
    w.connect("leave-notify-event", _out)
    return w

def styled_button(label, css_class):
    b = Gtk.Button(label=label)
    b.get_style_context().add_class(css_class)
    make_clickable(b)
    return b

def make_version_picker(version_names, version_ids, active_idx=0):
    state = {"idx": active_idx}
    outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    outer.get_style_context().add_class("hk-combo-outer")
    lbl = Gtk.Label(xalign=0)
    lbl.get_style_context().add_class("hk-combo-label")
    lbl.set_ellipsize(3)
    if version_names:
        lbl.set_text(version_names[active_idx])
    arrow = Gtk.Label(label="▾")
    arrow.get_style_context().add_class("hk-combo-arrow")
    outer.pack_start(lbl, True, True, 0)
    outer.pack_start(arrow, False, False, 0)
    btn = Gtk.Button()
    btn.get_style_context().add_class("hk-combo-btn")
    btn.set_size_request(200, 42)
    btn.add(outer)
    make_clickable(btn)
    popover = Gtk.Popover()
    popover.set_relative_to(btn)
    popover.set_position(Gtk.PositionType.TOP)
    pop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    pop_box.get_style_context().add_class("hk-combo-popover")
    pop_box.set_size_request(240, -1)
    def _select(i):
        state["idx"] = i
        lbl.set_text(version_names[i])
        popover.popdown()
    for i, name in enumerate(version_names):
        row_btn = Gtk.Button(label=name)
        row_btn.get_style_context().add_class("hk-combo-item")
        if i == active_idx:
            row_btn.get_style_context().add_class("hk-combo-item-active")
        row_btn.connect("clicked", lambda _, idx=i: _select(idx))
        make_clickable(row_btn)
        pop_box.pack_start(row_btn, False, False, 0)
    popover.add(pop_box)
    pop_box.show_all()
    btn.connect("clicked", lambda _: popover.popup())
    return btn, lambda: state["idx"]

def format_playtime(seconds):
    h = int(seconds) // 3600; m = (int(seconds) % 3600) // 60; s = int(seconds) % 60
    if h > 0: return f"{h}h {m}m"
    if m > 0: return f"{m}m"
    return f"{s}s"

def show_progress_window(parent, title, msg):
    win = Gtk.Window(title=title); win.set_modal(True)
    win.set_transient_for(parent); win.set_default_size(480, 110); win.set_resizable(False)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_top(16); box.set_margin_bottom(16)
    box.set_margin_start(16); box.set_margin_end(16)
    lbl = Gtk.Label(label=msg, xalign=0)
    pbar = Gtk.ProgressBar(); pbar.set_pulse_step(0.05)
    box.pack_start(lbl, False, False, 0); box.pack_start(pbar, False, False, 0)
    win.add(box); win.show_all()
    return win, pbar

def flatten_zip(zip_path, target_folder, progress_cb=None):
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist(); total = max(1, len(names))
        prefix = os.path.commonprefix(names).rstrip("/")
        for i, member in enumerate(names):
            rel = member[len(prefix)+1:] if (prefix and member.startswith(prefix+"/")) else member
            if not rel or member.endswith("/"):
                if progress_cb: GLib.idle_add(progress_cb, (i+1)/total)
                continue
            dest = os.path.join(target_folder, rel)
            os.makedirs(os.path.dirname(dest) or target_folder, exist_ok=True)
            with open(dest, "wb") as out: out.write(z.read(member))
            if progress_cb: GLib.idle_add(progress_cb, (i+1)/total)

NOTIF_COLORS = {
    "error":   ("#ef4444", "✕"), "warning": ("#ffa000", "⚠"),
    "info":    ("#6366f1", "ℹ"), "success": ("#3fcf8e", "✓"),
}
def load_notifications():   return load_json_file(NOTIFY_FILE, [])
def save_notifications(ns): save_json_file(NOTIFY_FILE, ns)

def append_gamelog(line):
    try:
        with open(GAMELOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {line}\n")
    except Exception: pass

def read_gamelog():
    try:
        with open(GAMELOG_FILE) as f: return f.read()
    except Exception: return ""


# ════════════════════════════════════════════
#  WORLD / SKIN / PACK HELPERS
# ════════════════════════════════════════════
GAMEMODES = {0: "Survival", 1: "Creative", 2: "Adventure", 3: "Spectator"}

def parse_level_dat(path):
    info = {"seed": "—", "gamemode": "—"}
    try:
        with open(path, "rb") as f:
            f.read(8)
            data = f.read()
        i = 0
        while i < len(data) - 20:
            tag = data[i]
            if tag in (3, 4):
                try:
                    nlen = struct.unpack_from('<H', data, i+1)[0]
                    if 1 <= nlen <= 64 and i+3+nlen+8 <= len(data):
                        name = data[i+3:i+3+nlen].decode('utf-8', errors='ignore')
                        vo = i + 3 + nlen
                        if name == 'RandomSeed' and tag == 4:
                            info['seed'] = str(struct.unpack_from('<q', data, vo)[0])
                        elif name == 'GameType' and tag == 3:
                            gm = struct.unpack_from('<i', data, vo)[0]
                            info['gamemode'] = GAMEMODES.get(gm, f"Mode {gm}")
                except Exception: pass
            i += 1
    except Exception: pass
    return info

def find_active_skin():
    if not os.path.isdir(CUSTOM_SKINS): return None
    pngs = [(os.path.getmtime(os.path.join(CUSTOM_SKINS, f)),
             os.path.join(CUSTOM_SKINS, f))
            for f in os.listdir(CUSTOM_SKINS) if f.lower().endswith('.png')]
    return sorted(pngs, reverse=True)[0][1] if pngs else None

def detect_pack_type_from_zip(zip_path):
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for n in z.namelist():
                if os.path.basename(n) == "manifest.json":
                    try:
                        data = json.loads(z.read(n).decode("utf-8", errors="ignore"))
                        for m in (data.get("modules") or []):
                            t = str(m.get("type", "")).lower()
                            if t in ("data","script","javascript","behavior"): return "behavior"
                            if t in ("resources","resource"): return "resource"
                    except Exception: pass
    except Exception: pass
    return "resource"

def import_mcaddon(addon_path, progress_cb=None):
    import tempfile
    results = []
    try:
        with zipfile.ZipFile(addon_path, "r") as z:
            names = z.namelist()
            root_packs = [n for n in names if n.endswith('.mcpack') and n.count('/') == 0]
            if root_packs:
                with tempfile.TemporaryDirectory() as tmp:
                    for i, pname in enumerate(root_packs):
                        pfile = os.path.join(tmp, pname)
                        with open(pfile, "wb") as pf: pf.write(z.read(pname))
                        ptype = detect_pack_type_from_zip(pfile)
                        dest_root = BEHAVIOUR_DIR if ptype == "behavior" else RESOURCE_DIR
                        pack_name = os.path.splitext(pname)[0]
                        dest = os.path.join(dest_root, pack_name)
                        n2 = 1
                        while os.path.exists(dest): dest = os.path.join(dest_root, f"{pack_name}_{n2}"); n2 += 1
                        os.makedirs(dest, exist_ok=True)
                        with zipfile.ZipFile(pfile, "r") as pz: pz.extractall(dest)
                        results.append((pack_name, ptype))
                        if progress_cb: GLib.idle_add(progress_cb, (i+1)/len(root_packs))
            else:
                top_folders = sorted({n.split('/')[0] for n in names if '/' in n and n.split('/')[0]})
                with tempfile.TemporaryDirectory() as tmp:
                    z.extractall(tmp)
                    for i, folder in enumerate(top_folders):
                        fpath = os.path.join(tmp, folder)
                        if not os.path.isdir(fpath): continue
                        mf = os.path.join(fpath, "manifest.json")
                        ptype = "resource"
                        if os.path.exists(mf):
                            try:
                                data = json.load(open(mf))
                                for m in (data.get("modules") or []):
                                    t = str(m.get("type","")).lower()
                                    if t in ("data","script","javascript","behavior"): ptype="behavior"; break
                                    if t in ("resources","resource"): ptype="resource"; break
                            except Exception: pass
                        dest_root = BEHAVIOUR_DIR if ptype == "behavior" else RESOURCE_DIR
                        dest = os.path.join(dest_root, folder)
                        n2 = 1
                        while os.path.exists(dest): dest = os.path.join(dest_root, f"{folder}_{n2}"); n2 += 1
                        shutil.copytree(fpath, dest)
                        results.append((folder, ptype))
                        if progress_cb: GLib.idle_add(progress_cb, (i+1)/max(1,len(top_folders)))
    except Exception as e: print(f"[mcaddon] {e}")
    return results


# ════════════════════════════════════════════
#  SERVER CONTROL PANEL
# ════════════════════════════════════════════
class ServerControlPanel(Gtk.Window):
    def __init__(self, parent, server_name, server_dir):
        super().__init__(title=f"Server — {server_name}")
        self.set_default_size(920, 680); self.set_transient_for(parent)
        self.server_dir = server_dir; self.server_process = None
        self._start_time = None; self._uptime_timer = None
        self._build(server_name); self.show_all()

    def _build(self, server_name):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.add(root)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        bar.get_style_context().add_class("server-status-bar")
        bar.set_margin_start(14); bar.set_margin_end(14)
        bar.set_margin_top(10); bar.set_margin_bottom(10)
        nc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); nc.set_valign(Gtk.Align.CENTER)
        nl = Gtk.Label(xalign=0); nl.set_markup(f"<b>{server_name}</b>")
        nl.get_style_context().add_class("version-name")
        self.status_lbl = Gtk.Label(xalign=0)
        self.status_lbl.set_markup("<span color='#f85149'>● Offline</span>")
        nc.pack_start(nl, False, False, 0); nc.pack_start(self.status_lbl, False, False, 0)
        bar.pack_start(nc, True, True, 0)
        def _stat(lbl):
            b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            b.get_style_context().add_class("server-stat-box"); b.set_halign(Gtk.Align.CENTER)
            v = Gtk.Label(label="—"); v.get_style_context().add_class("server-stat-value")
            l = Gtk.Label(label=lbl); l.get_style_context().add_class("server-stat-label")
            b.pack_start(v, False, False, 0); b.pack_start(l, False, False, 0)
            return b, v
        uc, self.uptime_val  = _stat("UPTIME")
        pc, self.players_val = _stat("PLAYERS")
        dc, self.pid_val     = _stat("PID")
        for c in (uc, pc, dc): bar.pack_start(c, False, False, 0)
        root.pack_start(bar, False, False, 0)
        br = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        br.set_margin_start(14); br.set_margin_end(14)
        br.set_margin_top(10); br.set_margin_bottom(10)
        self.start_btn   = styled_button("▶  Start",   "small-play")
        self.stop_btn    = styled_button("■  Stop",    "del-btn")
        self.restart_btn = styled_button("⟳  Restart", "secondary-btn")
        self.stop_btn.set_sensitive(False); self.restart_btn.set_sensitive(False)
        self.start_btn.connect("clicked", self._on_start)
        self.stop_btn.connect("clicked",  self._on_stop)
        self.restart_btn.connect("clicked", self._on_restart)
        for b in (self.start_btn, self.stop_btn, self.restart_btn): br.pack_start(b, False, False, 0)
        clr = styled_button("Clear", "mini-btn")
        clr.connect("clicked", lambda *_: self.console_buf.set_text(""))
        br.pack_end(clr, False, False, 0); root.pack_start(br, False, False, 0)
        root.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True); sw.set_margin_start(14); sw.set_margin_end(14); sw.set_margin_top(8)
        self.console_view = Gtk.TextView()
        self.console_view.set_editable(False); self.console_view.set_monospace(True)
        self.console_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.console_view.get_style_context().add_class("console")
        self.console_buf = self.console_view.get_buffer()
        sw.add(self.console_view); root.pack_start(sw, True, True, 0)
        cr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cr.set_margin_start(14); cr.set_margin_end(14); cr.set_margin_top(8); cr.set_margin_bottom(14)
        self.cmd_entry = Gtk.Entry(); self.cmd_entry.set_placeholder_text("Enter server command…")
        self.cmd_entry.connect("activate", self._on_send)
        sb = styled_button("Send", "small-play"); sb.connect("clicked", self._on_send)
        cr.pack_start(self.cmd_entry, True, True, 0); cr.pack_start(sb, False, False, 0)
        root.pack_start(cr, False, False, 0)

    def _append(self, text):
        it = self.console_buf.get_end_iter()
        self.console_buf.insert(it, f"[{time.strftime('%H:%M:%S')}] {text}\n")
        mk = self.console_buf.create_mark(None, it, False)
        self.console_view.scroll_to_mark(mk, 0.0, True, 0.0, 1.0)

    def _on_start(self, *_):
        if self.server_process: return
        self.status_lbl.set_markup("<span color='#f0c000'>● Starting…</span>")
        ep = os.path.join(self.server_dir, "bedrock_server")
        if not os.path.exists(ep):
            self._append("ERROR: bedrock_server binary not found.")
            self.status_lbl.set_markup("<span color='#f85149'>● Error</span>"); return
        try:
            self.server_process = subprocess.Popen(
                [ep], cwd=self.server_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE, text=True, bufsize=1)
        except Exception as e:
            self._append(f"ERROR: {e}")
            self.status_lbl.set_markup("<span color='#f85149'>● Error</span>"); return
        self._start_time = time.time()
        self.start_btn.set_sensitive(False); self.stop_btn.set_sensitive(True); self.restart_btn.set_sensitive(True)
        self.status_lbl.set_markup("<span color='#3fcf8e'>● Online</span>")
        self.pid_val.set_text(str(self.server_process.pid))
        def _tick():
            if self.server_process:
                self.uptime_val.set_text(format_playtime(time.time() - self._start_time)); return True
            return False
        self._uptime_timer = GLib.timeout_add_seconds(1, _tick)
        def _read():
            try:
                for line in iter(self.server_process.stdout.readline, ""):
                    if line:
                        s = line.rstrip(); GLib.idle_add(self._append, s)
                        low = s.lower()
                        if "players online:" in low:
                            try:
                                n = low.split("players online:")[1].strip().split()[0]
                                GLib.idle_add(self.players_val.set_text, n)
                            except Exception: pass
            except Exception as e: GLib.idle_add(self._append, f"[err] {e}")
            finally: GLib.idle_add(self._stopped)
        threading.Thread(target=_read, daemon=True).start()

    def _on_stop(self, *_):
        if not self.server_process: return
        try:
            self.server_process.stdin.write("stop\n"); self.server_process.stdin.flush()
            self.server_process.wait(timeout=12)
        except subprocess.TimeoutExpired: self.server_process.kill()
        except Exception: pass

    def _on_restart(self, *_):
        self._on_stop(); GLib.timeout_add(2200, self._on_start)

    def _on_send(self, *_):
        if not self.server_process: return
        cmd = self.cmd_entry.get_text().strip()
        if not cmd: return
        try:
            self.server_process.stdin.write(cmd + "\n"); self.server_process.stdin.flush()
            self._append(f"> {cmd}"); self.cmd_entry.set_text("")
        except Exception as e: self._append(f"[err] {e}")

    def _stopped(self):
        if self._uptime_timer: GLib.source_remove(self._uptime_timer); self._uptime_timer = None
        self.server_process = None
        self.start_btn.set_sensitive(True); self.stop_btn.set_sensitive(False); self.restart_btn.set_sensitive(False)
        self.status_lbl.set_markup("<span color='#f85149'>● Offline</span>")
        for v in (self.uptime_val, self.players_val, self.pid_val): v.set_text("—")
        self._append("Server stopped.")

# ════════════════════════════════════════════
#  SKIN PREVIEW WIDGET
# ════════════════════════════════════════════
_COS = math.cos(math.pi / 6)
_SIN = math.sin(math.pi / 6)

class SkinView3D(Gtk.DrawingArea):
    S = 7
    def __init__(self):
        super().__init__()
        self._pixels = None
        self._ph = 64
        self._wide = False
        S = self.S
        W = int(16 * S + 8 * _COS * S) + 16
        H = int(32 * S + 8 * _SIN * S) + 20
        self.set_size_request(W, H)
        self.connect("draw", self._on_draw)

    def load_skin(self, path):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(path)
            if not pb.get_has_alpha():
                pb = pb.add_alpha(False, 0, 0, 0)
            if pb.get_width() != 64:
                nh = pb.get_height() * 64 // pb.get_width()
                pb = pb.scale_simple(64, nh, GdkPixbuf.InterpType.NEAREST)
            self._wide = pb.get_height() >= 48
            self._ph = pb.get_height()
            self._pixels = bytearray(pb.get_pixels())
            self.queue_draw()
        except Exception as e:
            print(f"[SkinView3D] {e}")

    def _px(self, x, y):
        if not self._pixels or x < 0 or y < 0 or x >= 64 or y >= self._ph:
            return (0, 0, 0, 0)
        o = (y * 64 + x) * 4
        return tuple(self._pixels[o:o + 4])

    def _face(self, ux, uy, uw, uh, flip=False):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, uw, uh)
        data = surf.get_data(); st = surf.get_stride()
        for sy in range(uh):
            for sx in range(uw):
                fx = ux + (uw - 1 - sx if flip else sx)
                r, g, b, a = self._px(fx, uy + sy)
                o = sy * st + sx * 4
                data[o] = b; data[o+1] = g; data[o+2] = r; data[o+3] = a
        surf.mark_dirty()
        return surf

    def _mat_front(self, dx, dy): S = self.S; return cairo.Matrix(S, 0, 0, S, dx, dy)
    def _mat_side(self, dx, dy): S = self.S; return cairo.Matrix(_COS*S, -_SIN*S, 0, S, dx, dy)
    def _mat_top(self, dx, dy, depth):
        S = self.S; D = depth
        return cairo.Matrix(S, 0, -_COS*S, _SIN*S, dx + D*_COS*S, dy - D*_SIN*S)

    def _paint(self, cr, surf, mat, shade=1.0):
        cr.save(); cr.transform(mat)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint_with_alpha(shade); cr.restore()

    def _part(self, cr, f_uv, s_uv, t_uv, dx, dy, fw, fh, depth,
              shade_s=0.70, shade_t=0.85, of_uv=None, os_uv=None, ot_uv=None):
        S = self.S
        def _p(uv, w, h, mat, shade):
            if uv: self._paint(cr, self._face(uv[0], uv[1], w, h), mat, shade)
        _p(f_uv, fw, fh, self._mat_front(dx, dy), 1.0)
        _p(s_uv, depth, fh, self._mat_side(dx + fw*S, dy), shade_s)
        _p(t_uv, fw, depth, self._mat_top(dx, dy, depth), shade_t)
        _p(of_uv, fw, fh, self._mat_front(dx, dy), 1.0)
        _p(os_uv, depth, fh, self._mat_side(dx + fw*S, dy), shade_s)
        _p(ot_uv, fw, depth, self._mat_top(dx, dy, depth), shade_t)

    def _on_draw(self, widget, cr):
        alloc = widget.get_allocation(); W, H = alloc.width, alloc.height; S = self.S; wide = self._wide
        cr.set_operator(cairo.OPERATOR_CLEAR); cr.paint(); cr.set_operator(cairo.OPERATOR_OVER)
        if not self._pixels:
            cr.set_source_rgba(0.55, 0.55, 0.55, 0.6); cr.select_font_face("sans-serif")
            cr.set_font_size(12); te = cr.text_extents("No skin")
            cr.move_to((W - te[2]) / 2, H / 2); cr.show_text("No skin")
        body_x = (W - 8*S - int(8*_COS*S)) // 2; feet_y = H - 6
        leg_y = feet_y - 12*S; body_y = leg_y - 12*S; head_y = body_y - 8*S; arm_y = body_y
        leg_rx = body_x; leg_lx = body_x + 4*S; arm_rx = body_x - 4*S; arm_lx = body_x + 8*S; head_x = body_x
        p = self._part
        p(cr, (4,20),(8,20),(4,16), leg_rx, leg_y, 4,12,4,
          of_uv=(4,36) if wide else None, os_uv=(8,36) if wide else None, ot_uv=(4,32) if wide else None)
        if wide:
            p(cr, (20,52),(24,52),(20,48), leg_lx, leg_y, 4,12,4, of_uv=(4,52), os_uv=(8,52), ot_uv=(4,48))
        else:
            p(cr, (4,20),(0,20),(4,16), leg_lx, leg_y, 4,12,4)
        p(cr, (20,20),(28,20),(20,16), body_x, body_y, 8,12,4,
          of_uv=(20,36) if wide else None, os_uv=(28,36) if wide else None, ot_uv=(20,32) if wide else None)
        p(cr, (44,20), None,(44,16), arm_rx, arm_y, 4,12,4,
          of_uv=(44,36) if wide else None, ot_uv=(44,32) if wide else None)
        if wide:
            p(cr, (36,52),(40,52),(36,48), arm_lx, arm_y, 4,12,4, of_uv=(52,52), os_uv=(56,52), ot_uv=(52,48))
        else:
            p(cr, (44,20),(48,20),(44,16), arm_lx, arm_y, 4,12,4)
        p(cr, (8,8),(16,8),(8,0), head_x, head_y, 8,8,8, of_uv=(40,8), os_uv=(48,8), ot_uv=(40,0))


# ════════════════════════════════════════════
#  ANIMATED SPLASH SCREEN
#  Draws directly on the launcher's overlay — NOT a separate window.
# ════════════════════════════════════════════
class SplashScreen:
    """
    Attaches a full-cover DrawingArea to the launcher's Gtk.Overlay.
    Phases:
      fade_in  (400 ms)
      hold     (random 1–6 s)
      fade_out (400 ms)
      → on_done() called, DrawingArea removed
    """

    _TICK_MS    = 16
    _FADEIN_MS  = 400
    _FADEOUT_MS = 400

    def __init__(self, overlay, on_done):
        self._overlay    = overlay
        self._on_done    = on_done
        self._start      = time.time()
        self._tick_count = 0
        self._hold_ms    = random.randint(1000, 6000)   # 1–6 seconds

        self._alpha    = 0.0
        self._logo_s   = 0.4
        self._progress = 0.0

        # Load logo
        self._logo_pb = None
        logo_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "assets", "icons", "app.png")
        if os.path.exists(logo_path):
            try:
                self._logo_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    logo_path, 96, 96, True)
            except Exception:
                pass

        # Full-cover drawing area — sits on top of everything
        self._da = Gtk.DrawingArea()
        self._da.set_hexpand(True)
        self._da.set_vexpand(True)
        self._da.set_halign(Gtk.Align.FILL)
        self._da.set_valign(Gtk.Align.FILL)
        self._da.connect("draw", self._draw)
        # Pass through no events so launcher underneath stays quiet
        self._da.add_events(0)
        self._overlay.add_overlay(self._da)
        self._overlay.set_overlay_pass_through(self._da, False)
        self._overlay.show_all()

        GLib.timeout_add(self._TICK_MS, self._tick)

    # ── timing ────────────────────────────────────────────────────
    @staticmethod
    def _ease_out(t):
        t = max(0.0, min(1.0, t))
        return 1.0 - (1.0 - t) ** 3

    def _tick(self):
        elapsed_ms = (time.time() - self._start) * 1000
        self._tick_count += 1

        fade_in_end  = self._FADEIN_MS
        hold_end     = fade_in_end + self._hold_ms
        fade_out_end = hold_end + self._FADEOUT_MS

        if elapsed_ms < fade_in_end:
            t = elapsed_ms / fade_in_end
            self._alpha    = self._ease_out(t)
            self._logo_s   = 0.4 + 0.6 * self._ease_out(t)
            self._progress = 0.0

        elif elapsed_ms < hold_end:
            t = (elapsed_ms - fade_in_end) / self._hold_ms
            self._alpha    = 1.0
            self._logo_s   = 1.0
            self._progress = t

        elif elapsed_ms < fade_out_end:
            t = (elapsed_ms - hold_end) / self._FADEOUT_MS
            self._alpha    = 1.0 - self._ease_out(t)
            self._logo_s   = 1.0
            self._progress = 1.0

        else:
            # Remove overlay DA, call done
            try:
                self._overlay.remove(self._da)
            except Exception:
                pass
            self._on_done()
            return False

        self._da.queue_draw()
        return True

    # ── drawing ───────────────────────────────────────────────────
    def _draw(self, widget, cr):
        alloc = widget.get_allocation()
        W, H  = alloc.width, alloc.height
        cx    = W / 2
        a     = max(0.0, min(1.0, self._alpha))

        # Solid dark cover — fills the entire launcher
        cr.set_source_rgba(0.04, 0.06, 0.09, a * 0.97)
        cr.rectangle(0, 0, W, H)
        cr.fill()

        # Subtle green vignette at center
        logo_cy = H * 0.38
        pat = cairo.RadialGradient(cx, logo_cy, 10, cx, logo_cy, min(W, H) * 0.45)
        pat.add_color_stop_rgba(0,   0.25, 0.81, 0.55, a * 0.10)
        pat.add_color_stop_rgba(1.0, 0.0,  0.0,  0.0,  0.0)
        cr.set_source(pat)
        cr.rectangle(0, 0, W, H)
        cr.fill()

        # ── Logo ──────────────────────────────────────────────────
        s = self._logo_s
        if self._logo_pb:
            lw = self._logo_pb.get_width()  * s
            lh = self._logo_pb.get_height() * s
            cr.save()
            cr.translate(cx - lw / 2, logo_cy - lh / 2)
            cr.scale(s, s)
            Gdk.cairo_set_source_pixbuf(cr, self._logo_pb, 0, 0)
            cr.paint_with_alpha(a)
            cr.restore()
        else:
            cr.save()
            cr.select_font_face("sans-serif",
                cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(56 * s)
            cr.set_source_rgba(0.25, 0.81, 0.55, a)
            te = cr.text_extents("⛏")
            cr.move_to(cx - te[2] / 2, logo_cy + te[3] / 2)
            cr.show_text("⛏")
            cr.restore()

        # ── Spinning arc around logo ──────────────────────────────
        arc_r   = 62
        arc_w   = 3.0
        angle   = (self._tick_count * self._TICK_MS / 1000.0) * math.pi * 1.6
        arc_len = math.pi * 0.7

        # Track
        cr.set_source_rgba(1, 1, 1, a * 0.06)
        cr.set_line_width(arc_w)
        cr.arc(cx, logo_cy, arc_r, 0, 2 * math.pi)
        cr.stroke()

        # Arc
        cr.set_source_rgba(0.25, 0.81, 0.55, a * 0.85)
        cr.set_line_width(arc_w)
        cr.arc(cx, logo_cy, arc_r, angle, angle + arc_len)
        cr.stroke()

        # Glowing dot at tip
        tip_x = cx      + arc_r * math.cos(angle + arc_len)
        tip_y = logo_cy + arc_r * math.sin(angle + arc_len)
        dot_pat = cairo.RadialGradient(tip_x, tip_y, 0, tip_x, tip_y, 7)
        dot_pat.add_color_stop_rgba(0,   0.25, 0.81, 0.55, a * 0.90)
        dot_pat.add_color_stop_rgba(1.0, 0.25, 0.81, 0.55, 0.0)
        cr.set_source(dot_pat)
        cr.arc(tip_x, tip_y, 7, 0, 2 * math.pi)
        cr.fill()

        # ── App name ──────────────────────────────────────────────
        cr.select_font_face("sans-serif",
            cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(19)
        cr.set_source_rgba(0.90, 0.93, 0.96, a)
        name = "Bedrock Rock Launcher"
        te   = cr.text_extents(name)
        cr.move_to(cx - te[2] / 2, H * 0.63)
        cr.show_text(name)

        # ── Version ───────────────────────────────────────────────
        cr.set_font_size(11)
        cr.set_source_rgba(0.25, 0.81, 0.55, a * 0.80)
        ver = f"v{LAUNCHER_VERSION}"
        te  = cr.text_extents(ver)
        cr.move_to(cx - te[2] / 2, H * 0.69)
        cr.show_text(ver)

        # ── Progress bar ──────────────────────────────────────────
        bar_w = W * 0.35
        bar_h = 3
        bar_x = cx - bar_w / 2
        bar_y = H * 0.80
        bar_r = bar_h / 2

        # Track
        self._rounded_rect(cr, bar_x, bar_y, bar_w, bar_h, bar_r)
        cr.set_source_rgba(1, 1, 1, a * 0.07)
        cr.fill()

        # Fill
        fill_w = max(bar_r * 2, bar_w * self._progress)
        self._rounded_rect(cr, bar_x, bar_y, fill_w, bar_h, bar_r)
        cr.set_source_rgba(0.25, 0.81, 0.55, a * 0.90)
        cr.fill()

        # Shimmer at fill edge
        if fill_w > bar_r * 2:
            glow = cairo.LinearGradient(bar_x, 0, bar_x + fill_w, 0)
            glow.add_color_stop_rgba(0,   0.25, 0.81, 0.55, 0.0)
            glow.add_color_stop_rgba(0.7, 0.25, 0.81, 0.55, 0.0)
            glow.add_color_stop_rgba(1.0, 0.55, 0.95, 0.75, a * 0.55)
            self._rounded_rect(cr, bar_x, bar_y, fill_w, bar_h, bar_r)
            cr.set_source(glow)
            cr.fill()

        # ── Loading dots ──────────────────────────────────────────
        dot_labels = ["Loading", "Loading.", "Loading..", "Loading..."]
        dot_text   = dot_labels[(self._tick_count // 10) % 4]
        cr.set_font_size(10)
        cr.set_source_rgba(0.45, 0.50, 0.56, a * 0.65)
        te = cr.text_extents(dot_text)
        cr.move_to(cx - te[2] / 2, H * 0.88)
        cr.show_text(dot_text)

    @staticmethod
    def _rounded_rect(cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + r,     y + r,     r, math.pi,       1.5 * math.pi)
        cr.arc(x + w - r, y + r,     r, 1.5 * math.pi, 0)
        cr.arc(x + w - r, y + h - r, r, 0,             0.5 * math.pi)
        cr.arc(x + r,     y + h - r, r, 0.5 * math.pi, math.pi)
        cr.close_path()


# ════════════════════════════════════════════
#  MAIN LAUNCHER WINDOW
# ════════════════════════════════════════════
class Launcher(Gtk.Window):
    _nav_buttons  = {}
    _current_page = "home"

    _BUILTIN_CSS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "default.css")).read() if os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "default.css")) else ""

    def __init__(self):
        super().__init__(title="Minecraft Launcher")
        self.set_default_size(1120, 760); self.set_resizable(True)
        icon_path = os.path.join(ASSETS, "icons", "app.png")
        if os.path.exists(icon_path):
            try: self.set_icon_from_file(icon_path)
            except Exception: pass
        self._session_start = time.time()
        self._log_tag_table = None
        self._load_css()
        self._build_ui()
        try: self.set_position(Gtk.WindowPosition.CENTER)
        except Exception: pass
        self._rebuild_home()
        self.stack.set_visible_child(self.home_page)
        GLib.idle_add(self._show_pending_notifications)

        # ── Keyboard shortcuts ────────────────────────────────────
        self._accel_group = None
        self._apply_shortcuts()

        # ── Splash screen — only on real startup, not on reload ───
        if load_settings().get("splash_screen", True) and "--no-splash" not in sys.argv:
            self._main_root.hide()
            self._splash = SplashScreen(self._top_overlay, self._on_splash_done)
        else:
            self._splash = None

    # ── SHORTCUTS ─────────────────────────────────────────────────────────────
    def _apply_shortcuts(self):
        """(Re)register all keyboard shortcuts from saved settings."""
        if self._accel_group:
            self.remove_accel_group(self._accel_group)
        ag = Gtk.AccelGroup()
        self.add_accel_group(ag)
        self._accel_group = ag

        action_map = {
            "home":     self._show_home,
            "versions": self._show_versions,
            "servers":  self._show_servers,
            "storage":  self._show_storage,
            "import":   self._show_import,
            "settings": self._show_settings,
            "play":     self._profile_play,
            "reload":   self._restart,
            "help":     self._show_shortcuts_help,
        }
        shortcuts = load_shortcuts()
        for action, cb in action_map.items():
            key_str = shortcuts.get(action, "")
            if not key_str: continue
            try:
                k, m = Gtk.accelerator_parse(key_str)
                if k:
                    ag.connect(k, m, Gtk.AccelFlags.VISIBLE,
                               lambda *_, fn=cb: fn() or True)
            except Exception as e:
                print(f"[shortcuts] {action}: {e}", flush=True)

    # ── CSS ──────────────────────────────────────────────────────────────────
    def _load_css(self):
        os.makedirs(THEME_DIR, exist_ok=True)
        # Write the bundled default CSS from the file next to the script
        default_path = os.path.join(THEME_DIR, "default.css")
        bundled = os.path.join(BASE, "default.css")
        if os.path.exists(bundled):
            try: shutil.copy2(bundled, default_path)
            except Exception: pass
        elif not os.path.exists(default_path) and self._BUILTIN_CSS:
            try:
                with open(default_path, "w") as f: f.write(self._BUILTIN_CSS)
            except Exception: pass
        s  = load_settings()
        tf = os.path.join(THEME_DIR, s.get("theme", "default.css"))
        if not os.path.exists(tf): tf = default_path
        self._apply_css_file(tf)

    def _apply_css_file(self, path):
        if not path or not os.path.exists(path): return
        try:
            provider = Gtk.CssProvider()
            null_fd = os.open(os.devnull, os.O_WRONLY); saved = os.dup(2); os.dup2(null_fd, 2)
            try:    provider.load_from_path(path)
            finally: os.dup2(saved, 2); os.close(saved); os.close(null_fd)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception as e: print(f"[css] {e}", flush=True)

    def _apply_inline_css(self, widget, css_str):
        null_fd = os.open(os.devnull, os.O_WRONLY); saved = os.dup(2); os.dup2(null_fd, 2)
        try:
            p = Gtk.CssProvider(); p.load_from_data(css_str.encode())
        finally: os.dup2(saved, 2); os.close(saved); os.close(null_fd)
        widget.get_style_context().add_provider(p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ── BUILD UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top-level overlay — splash draws here, main UI sits underneath
        self._top_overlay = Gtk.Overlay()
        self._top_overlay.set_hexpand(True); self._top_overlay.set_vexpand(True)
        self.add(self._top_overlay)

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._top_overlay.add(root)
        self._main_root = root

        # ── Sidebar (narrower = 72 px, icon-only, no version label) ──
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(72, -1)
        sidebar.get_style_context().add_class("sidebar")
        root.pack_start(sidebar, False, False, 0)

        # Logo
        logo_path = os.path.join(ASSETS, "icons", "app.png")
        logo_box = Gtk.Box(); logo_box.set_size_request(72, 62)
        logo_box.set_halign(Gtk.Align.CENTER); logo_box.set_valign(Gtk.Align.CENTER)
        if os.path.exists(logo_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(logo_path, 48, 48, True)
                img = Gtk.Image.new_from_pixbuf(pb); img.set_halign(Gtk.Align.CENTER)
                logo_box.pack_start(img, True, True, 0)
            except Exception: pass
        sidebar.pack_start(logo_box, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_start(10); sep.set_margin_end(10); sep.set_margin_bottom(4)
        sidebar.pack_start(sep, False, False, 0)

        nav = [
            ("home",     "Home",     "home.png",     self._show_home),
            ("versions", "Versions", "anvil.png",    self._show_versions),
            ("servers",  "Servers",  "server.png",   self._show_servers),
            ("storage",  "Storage",  "storage.png",  self._show_storage),
            ("import",   "Import",   "import.png",   self._show_import),
            ("settings", "Settings", "settings.png", self._show_settings),
        ]
        for pid, lbl, icon, cb in nav:
            btn = self._nav_button(pid, lbl, icon, cb)
            self._nav_buttons[pid] = btn
            sidebar.pack_start(btn, False, False, 0)

        spacer = Gtk.Box(); spacer.set_vexpand(True)
        sidebar.pack_start(spacer, True, True, 0)

        # Theme-specific decoration art
        cur_theme = load_settings().get("theme", "default.css").replace(".css", "")
        self._theme_art = ThemeArtWidget(cur_theme)
        self._theme_art.set_valign(Gtk.Align.CENTER)
        sidebar.pack_start(self._theme_art, False, False, 0)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.set_margin_start(10); sep2.set_margin_end(10)
        sidebar.pack_start(sep2, False, False, 0)

        profile_btn = self._profile_nav_button()
        self._nav_buttons["profile"] = profile_btn
        sidebar.pack_start(profile_btn, False, False, 0)
        # ── NO version label in sidebar ──

        # Content area with notification overlay
        self._overlay = Gtk.Overlay(); self._overlay.set_hexpand(True); self._overlay.set_vexpand(True)
        root.pack_start(self._overlay, True, True, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(80)
        self.stack.set_hexpand(True); self.stack.set_vexpand(True)
        self._overlay.add(self.stack)

        self._notif_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._notif_vbox.set_halign(Gtk.Align.CENTER)
        self._notif_vbox.set_valign(Gtk.Align.START)
        self._notif_vbox.set_margin_top(18)
        self._notif_vbox.set_size_request(500, -1)
        self._overlay.add_overlay(self._notif_vbox)

        self.home_page     = self._page_box()
        self.versions_page = self._page_box()
        self.servers_page  = self._page_box()
        self.storage_page  = self._page_box()
        self.import_page   = self._create_import_page()
        self.settings_page = self._page_box()
        self.profile_page  = self._page_box()
        for name, page in (
            ("home", self.home_page), ("versions", self.versions_page),
            ("servers", self.servers_page), ("storage", self.storage_page),
            ("import", self.import_page),
            ("settings", self.settings_page), ("profile", self.profile_page),
        ):
            self.stack.add_named(page, name)

    def _page_box(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        b.set_hexpand(True); b.set_vexpand(True)
        return b

    # ── NAV BUTTONS — icon-only, 72×72, icons 26px ───────────────────────────
    _FALLBACK_ICONS = {
        "home.png":"⌂","anvil.png":"⚒","server.png":"▣",
        "storage.png":"📦","import.png":"↓","settings.png":"⚙",
    }

    def _nav_button(self, page_id, text, icon_file, callback):
        btn = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        btn.get_style_context().add_class("nav-btn")
        btn.set_size_request(72, 72); make_clickable(btn)
        btn.set_tooltip_text(text)   # tooltip instead of label
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        col.set_halign(Gtk.Align.CENTER); col.set_valign(Gtk.Align.CENTER)
        icon_path = os.path.join(ASSETS, "icons", icon_file)
        if os.path.exists(icon_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 32, 32, True)
                img = Gtk.Image.new_from_pixbuf(pb); img.set_halign(Gtk.Align.CENTER)
                col.pack_start(img, False, False, 0)
            except Exception:
                fb = Gtk.Label()
                fb.set_markup(f"<span size='large'>{self._FALLBACK_ICONS.get(icon_file,'●')}</span>")
                col.pack_start(fb, False, False, 0)
        else:
            fb = Gtk.Label()
            fb.set_markup(f"<span size='large'>{self._FALLBACK_ICONS.get(icon_file,'●')}</span>")
            col.pack_start(fb, False, False, 0)
        # Small label below icon (optional — visible enough at 72px height)
        lbl = Gtk.Label(label=text); lbl.get_style_context().add_class("nav-label")
        lbl.set_halign(Gtk.Align.CENTER); col.pack_start(lbl, False, False, 0)
        btn.add(col); btn.connect("clicked", lambda *_: callback())
        return btn

    def _profile_nav_button(self):
        btn = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        btn.get_style_context().add_class("profile-btn")
        btn.set_size_request(72, 72); make_clickable(btn)
        btn.set_tooltip_text("Profile")
        btn.connect("clicked", lambda *_: self._show_profile())
        self._rebuild_profile_btn_inner(btn)
        return btn

    def _rebuild_profile_btn_inner(self, btn=None):
        if btn is None: btn = self._nav_buttons.get("profile")
        if btn is None: return
        for c in list(btn.get_children()): btn.remove(c)
        p = load_profile()
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        col.set_halign(Gtk.Align.CENTER); col.set_valign(Gtk.Align.CENTER)

        # Avatar: custom picture → profile.png → initial letter fallback
        avatar_box = Gtk.Box(); avatar_box.set_size_request(34, 34)
        avatar_box.set_halign(Gtk.Align.CENTER)
        pic_path = p.get("profile_picture")
        loaded_pic = False
        if pic_path and os.path.exists(pic_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(pic_path, 34, 34, True)
                # Make circular via DrawingArea
                img = Gtk.Image.new_from_pixbuf(pb)
                self._apply_inline_css(avatar_box,
                    ".av-pic-nav { border-radius: 17px; border: 2px solid rgba(255,255,255,0.15); }")
                avatar_box.get_style_context().add_class("av-pic-nav")
                avatar_box.pack_start(img, True, True, 0)
                loaded_pic = True
            except Exception: pass
        if not loaded_pic:
            svg_path = os.path.join(ASSETS, "icons", "profile.png")
            if os.path.exists(svg_path):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(svg_path, 34, 34, True)
                    img = Gtk.Image.new_from_pixbuf(pb)
                    self._apply_inline_css(avatar_box,
                        ".av-svg-nav { border-radius: 17px; background: rgba(63,207,142,0.12); }")
                    avatar_box.get_style_context().add_class("av-svg-nav")
                    avatar_box.pack_start(img, True, True, 0)
                    loaded_pic = True
                except Exception: pass
        if not loaded_pic:
            # Fallback: initial in circle
            dot = Gtk.Box(); dot.set_size_request(34, 34)
            self._apply_inline_css(dot,
                ".nav-profile-dot { background-color:#3fcf8e; border-radius:17px; min-width:34px; min-height:34px; }")
            dot.get_style_context().add_class("nav-profile-dot")
            name = p.get("username","P")
            init = Gtk.Label()
            init.set_markup(f"<span weight='bold' color='#fff' size='small'>{(name or 'P')[0].upper()}</span>")
            init.set_halign(Gtk.Align.CENTER); init.set_valign(Gtk.Align.CENTER)
            dot.pack_start(init, True, True, 0)
            avatar_box.pack_start(dot, True, True, 0)

        col.pack_start(avatar_box, False, False, 0)
        # Show username/gamertag instead of generic "Profile"
        name = p.get("username","Player")
        short_name = (name or "Profile")[:8]
        lbl = Gtk.Label(label=short_name); lbl.get_style_context().add_class("nav-label")
        lbl.set_halign(Gtk.Align.CENTER); col.pack_start(lbl, False, False, 0)
        btn.add(col); btn.show_all()


    def _set_active_nav(self, page_id):
        for pid, btn in self._nav_buttons.items():
            ctx = btn.get_style_context()
            ctx.remove_class("nav-btn-active"); ctx.remove_class("profile-btn-active")
        btn = self._nav_buttons.get(page_id)
        if btn:
            btn.get_style_context().add_class(
                "profile-btn-active" if page_id == "profile" else "nav-btn-active")
        self._current_page = page_id

    # ── NAVIGATION ────────────────────────────────────────────────────────────
    def _show_home(self):     self._set_active_nav("home");     self._rebuild_home();     self.stack.set_visible_child(self.home_page)
    def _show_versions(self): self._set_active_nav("versions"); self._rebuild_versions(); self.stack.set_visible_child(self.versions_page)
    def _show_servers(self):  self._set_active_nav("servers");  self._rebuild_servers();  self.stack.set_visible_child(self.servers_page)
    def _show_storage(self):  self._set_active_nav("storage");  self._rebuild_storage();  self.stack.set_visible_child(self.storage_page)
    def _show_import(self):   self._set_active_nav("import");                             self.stack.set_visible_child(self.import_page)
    def _show_settings(self): self._set_active_nav("settings"); self._rebuild_settings(); self.stack.set_visible_child(self.settings_page)
    def _show_profile(self):  self._set_active_nav("profile");  self._rebuild_profile();  self.stack.set_visible_child(self.profile_page)

    def _clear(self, box):
        for c in list(box.get_children()): box.remove(c)

    def _page_header(self, title, extra=None):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(22); box.set_margin_bottom(14)
        box.set_margin_start(26); box.set_margin_end(26)
        lbl = Gtk.Label(label=title, xalign=0); lbl.get_style_context().add_class("page-title")
        box.pack_start(lbl, True, True, 0)
        if extra: box.pack_start(extra, False, False, 0)
        return box

    def _scrolled(self, child):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_margin_start(16); sw.set_margin_end(16); sw.set_margin_bottom(16)
        sw.add(child); sw.set_vexpand(True); sw.set_hexpand(True)
        return sw

    def _section_lbl(self, t):
        l = Gtk.Label(label=t, xalign=0)
        l.get_style_context().add_class("settings-section")
        l.set_margin_top(14); l.set_margin_bottom(4)
        return l

    # ══════════════════════════════════════════════
    #  HOME PAGE
    # ══════════════════════════════════════════════
    def _rebuild_home(self):
        if not hasattr(self, "home_page"): return
        self._clear(self.home_page)
        settings  = load_settings()
        bg_files  = self._list_bg_files()
        chosen_bg = settings.get("background", "home.png")
        if settings.get("random_background") and bg_files: chosen_bg = random.choice(bg_files)
        if chosen_bg not in bg_files and bg_files: chosen_bg = bg_files[0]
        bg_path = os.path.join(BG_DIR, chosen_bg)
        self._home_bg_pb = None
        if os.path.exists(bg_path):
            try: self._home_bg_pb = GdkPixbuf.Pixbuf.new_from_file(bg_path)
            except Exception: pass

        overlay = Gtk.Overlay()
        overlay.set_hexpand(True); overlay.set_vexpand(True)
        bg_da = Gtk.DrawingArea()
        bg_da.set_hexpand(True); bg_da.set_vexpand(True)
        bg_da.connect("draw", self._draw_home_bg)
        overlay.add(bg_da)

        version_ids, version_names = [], []
        for d in sorted(os.listdir(GAME_DIR)):
            ip = os.path.join(GAME_DIR, d, "version_info.json")
            if not os.path.isdir(os.path.join(GAME_DIR, d)) or not os.path.exists(ip): continue
            try: info = json.load(open(ip))
            except Exception: continue
            if info.get("beta") and not settings.get("allow_beta"): continue
            version_ids.append(info.get("version_id", d))
            version_names.append(info.get("display_name", d))

        ui = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        ui.set_hexpand(True); ui.set_vexpand(True)

        spacer = Gtk.Box(); spacer.set_vexpand(True)
        ui.pack_start(spacer, True, True, 0)

        # ── BOTTOM STRIP ──────────────────────────────────────────
        # Layout: [spacer fills left] [combo+edit near profile side] [PLAY button]
        # This satisfies request #2 — version picker near the left edge (profile side)
        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        strip.get_style_context().add_class("banner-play-strip")

        # Left padding spacer (pushes combo toward center-left)
        left_pad = Gtk.Box(); left_pad.set_size_request(0, 1)#change 0 to add more space
        strip.pack_start(left_pad, False, False, 0)

        get_active_ver = None
        if not version_ids:
            no_ver = Gtk.Label(label="No versions installed — use Import to add one")
            no_ver.get_style_context().add_class("banner-hint")
            no_ver.set_margin_start(8); no_ver.set_margin_top(10); no_ver.set_margin_bottom(10)
            strip.pack_start(no_ver, False, False, 0)
        else:
            def_id = settings.get("default_version")
            active_idx = version_ids.index(def_id) if def_id and def_id in version_ids else len(version_ids) - 1
            left_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            left_group.set_margin_top(10); left_group.set_margin_bottom(10)
            combo_btn, get_active_ver = make_version_picker(version_names, version_ids, active_idx)
            left_group.pack_start(combo_btn, False, False, 0)
            edit_btn = Gtk.Button()
            edit_btn.get_style_context().add_class("version-edit-btn")
            edit_btn.set_size_request(42, 42); edit_btn.set_tooltip_text("Edit version")
            make_clickable(edit_btn)
            edit_icon_path = os.path.join(ASSETS, "icons", "edit.png")
            if os.path.exists(edit_icon_path):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(edit_icon_path, 16, 16, True)
                    edit_btn.add(Gtk.Image.new_from_pixbuf(pb))
                except Exception: edit_btn.set_label("✏")
            else:
                edit_btn.set_label("✏")
            def _on_edit_click(_btn):
                i = get_active_ver()
                if 0 <= i < len(version_ids): self._edit_version(version_ids[i])
            edit_btn.connect("clicked", _on_edit_click)
            left_group.pack_start(edit_btn, False, False, 0)
            strip.pack_start(left_group, False, False, 0)

        mid_spacer = Gtk.Box(); mid_spacer.set_hexpand(True)
        strip.pack_start(mid_spacer, True, True, 0)

        play_btn = styled_button("▶  PLAY", "play-btn")
        play_btn.set_size_request(180, 48)
        play_btn.set_margin_end(16); play_btn.set_margin_top(10); play_btn.set_margin_bottom(10)
        if version_ids and get_active_ver:
            def _do_play(_):
                i = get_active_ver()
                if 0 <= i < len(version_ids): self._launch_version(version_ids[i])
            play_btn.connect("clicked", _do_play)
        else:
            play_btn.set_sensitive(False)
        strip.pack_start(play_btn, False, False, 0)
        ui.pack_start(strip, False, False, 0)

        overlay.add_overlay(ui)
        self.home_page.pack_start(overlay, True, True, 0)
        self.home_page.show_all()

    def _draw_home_bg(self, widget, cr):
        alloc = widget.get_allocation(); w, h = alloc.width, alloc.height
        if self._home_bg_pb:
            iw = self._home_bg_pb.get_width(); ih = self._home_bg_pb.get_height()
            scale = max(w / iw, h / ih)
            nw = max(1, int(iw * scale)); nh = max(1, int(ih * scale))
            scaled = self._home_bg_pb.scale_simple(nw, nh, GdkPixbuf.InterpType.BILINEAR)
            xo = (w - nw) // 2; yo = (h - nh) // 2
            Gdk.cairo_set_source_pixbuf(cr, scaled, xo, yo); cr.paint()
        else:
            cr.set_source_rgb(0.05, 0.07, 0.10); cr.paint()
        return False

    # ══════════════════════════════════════════════
    #  VERSIONS PAGE
    # ══════════════════════════════════════════════
    def _rebuild_versions(self):
        if not hasattr(self, "versions_page"): return
        self._clear(self.versions_page)
        self.versions_page.pack_start(self._page_header("Versions"), False, False, 0)
        lb = Gtk.ListBox(); lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.get_style_context().add_class("card-list"); lb.set_hexpand(True)
        settings = load_settings(); found = False
        for d in sorted(os.listdir(GAME_DIR)):
            vpath = os.path.join(GAME_DIR, d)
            ip = os.path.join(vpath, "version_info.json")
            if not os.path.isdir(vpath) or not os.path.exists(ip): continue
            try: info = json.load(open(ip))
            except Exception: info = {"display_name":d,"version_id":d,"beta":False}
            found = True; is_default = (info.get("version_id",d) == settings.get("default_version"))
            rw = Gtk.EventBox()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            row.get_style_context().add_class("version-card")
            row.set_margin_top(4); row.set_margin_bottom(4)
            row.set_margin_start(14); row.set_margin_end(14)
            rw.add(row)
            ib = Gtk.Box(); ib.set_size_request(52,52); ib.get_style_context().add_class("version-icon-box")
            ic = Gtk.Label(); ic.set_markup("<span size='x-large'>⛏</span>"); ib.pack_start(ic, True, True, 0)
            row.pack_start(ib, False, False, 0)
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); tb.set_valign(Gtk.Align.CENTER)
            nl = Gtk.Label(label=info.get("display_name",d), xalign=0); nl.get_style_context().add_class("version-name")
            il = Gtk.Label(label=f"ID: {info.get('version_id',d)}", xalign=0); il.get_style_context().add_class("version-id")
            tb.pack_start(nl, False, False, 0); tb.pack_start(il, False, False, 0)
            row.pack_start(tb, True, True, 0)
            br2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6); br2.set_valign(Gtk.Align.CENTER)
            b = Gtk.Label()
            b.set_markup("<b>BETA</b>" if info.get("beta") else "<b>STABLE</b>")
            b.get_style_context().add_class("badge-beta" if info.get("beta") else "badge-stable")
            br2.pack_start(b, False, False, 0)
            if is_default:
                db = Gtk.Label(); db.set_markup("<b>DEFAULT</b>"); db.get_style_context().add_class("badge-default")
                br2.pack_start(db, False, False, 0)
            row.pack_start(br2, False, False, 0)
            vid = info.get("version_id", d)
            btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6); btns.set_valign(Gtk.Align.CENTER)
            pb2 = styled_button("▶ Play", "small-play"); pb2.connect("clicked", lambda _, v=vid: self._launch_version(v))
            btns.pack_start(pb2, False, False, 0)
            mb = Gtk.MenuButton(); mb.set_label("⋯"); mb.get_style_context().add_class("more-btn"); make_clickable(mb)
            menu = Gtk.Menu()
            for mi_lbl, mi_cb in (
                ("Set as default", lambda _, v=vid: self._set_default_version(v)),
                ("Edit info…",     lambda _, v=vid: self._edit_version(v)),
                ("Delete",         lambda _, v=vid: self._delete_version(v)),
            ):
                mi = Gtk.MenuItem(label=mi_lbl); mi.connect("activate", mi_cb); menu.append(mi)
            menu.show_all(); mb.set_popup(menu); btns.pack_start(mb, False, False, 0)
            row.pack_start(btns, False, False, 0); lb.add(rw)
        if not found:
            em = Gtk.Label(label="No versions installed yet.\nUse Import → Import APK to add one.")
            em.get_style_context().add_class("muted-label"); em.set_margin_top(40); em.set_justify(Gtk.Justification.CENTER)
            lb.add(em)
        self.versions_page.pack_start(self._scrolled(lb), True, True, 0)
        self.versions_page.show_all()

    # ══════════════════════════════════════════════
    #  SERVERS PAGE
    # ══════════════════════════════════════════════
    def _rebuild_servers(self):
        if not hasattr(self, "servers_page"): return
        self._clear(self.servers_page)
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hdr.set_margin_top(22); hdr.set_margin_bottom(10)
        hdr.set_margin_start(26); hdr.set_margin_end(26)
        hdr_lbl = Gtk.Label(label="Servers", xalign=0); hdr_lbl.get_style_context().add_class("page-title")
        hdr.pack_start(hdr_lbl, True, True, 0)
        ab = styled_button("+ New Server", "small-play")
        ab.connect("clicked", self._create_server_dialog)
        hdr.pack_start(ab, False, False, 0)
        self.servers_page.pack_start(hdr, False, False, 0)
        self.servers_page.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        srv_lb = Gtk.ListBox(); srv_lb.set_selection_mode(Gtk.SelectionMode.NONE)
        srv_lb.get_style_context().add_class("card-list"); srv_lb.set_hexpand(True)
        servers = []
        if os.path.isdir(SERVER_DIR):
            for n in sorted(os.listdir(SERVER_DIR)):
                p = os.path.join(SERVER_DIR, n)
                if os.path.isdir(p): servers.append((n, p))
        if not servers:
            em = Gtk.Label(label="No servers yet.\nClick '+ New Server' to create one.")
            em.get_style_context().add_class("muted-label"); em.set_margin_top(40); em.set_justify(Gtk.Justification.CENTER)
            srv_lb.add(em)
        else:
            for sname, spath in servers:
                rw = Gtk.EventBox()
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
                row.get_style_context().add_class("version-card")
                row.set_margin_top(4); row.set_margin_bottom(4); row.set_margin_start(14); row.set_margin_end(14)
                rw.add(row)
                ic = Gtk.Label(); ic.set_markup("<span size='xx-large'>🖥</span>"); row.pack_start(ic, False, False, 0)
                tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); tb.set_valign(Gtk.Align.CENTER)
                nl = Gtk.Label(label=sname, xalign=0); nl.get_style_context().add_class("version-name")
                pl = Gtk.Label(label=spath, xalign=0);  pl.get_style_context().add_class("version-id")
                tb.pack_start(nl, False, False, 0); tb.pack_start(pl, False, False, 0)
                row.pack_start(tb, True, True, 0)
                if os.path.exists(os.path.join(spath, "bedrock_server")):
                    rb = Gtk.Label(); rb.set_markup("<b>READY</b>"); rb.get_style_context().add_class("badge-stable")
                    row.pack_start(rb, False, False, 0)
                btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6); btns.set_valign(Gtk.Align.CENTER)
                opb = styled_button("Open Panel", "small-play"); opb.connect("clicked", lambda _, n=sname, p=spath: ServerControlPanel(self, n, p))
                db2 = styled_button("Delete", "del-btn"); db2.connect("clicked", lambda _, p=spath: self._delete_server(p))
                btns.pack_start(opb, False, False, 0); btns.pack_start(db2, False, False, 0)
                row.pack_start(btns, False, False, 0); srv_lb.add(rw)
        self.servers_page.pack_start(self._scrolled(srv_lb), True, True, 0)
        self.servers_page.show_all()

    # ══════════════════════════════════════════════
    #  STORAGE
    # ══════════════════════════════════════════════
    def _rebuild_storage(self, restore_tab=None):
        if not hasattr(self, "storage_page"): return
        active_tab = restore_tab or getattr(self, "_storage_active_tab", "rp")
        self._clear(self.storage_page)

        # ── Header row with title + search entry ──────────────────
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hdr.set_margin_top(22); hdr.set_margin_bottom(10)
        hdr.set_margin_start(26); hdr.set_margin_end(26)
        hdr_lbl = Gtk.Label(label="Storage", xalign=0)
        hdr_lbl.get_style_context().add_class("page-title")
        hdr.pack_start(hdr_lbl, True, True, 0)
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Filter…")
        search.set_size_request(220, -1)
        hdr.pack_start(search, False, False, 0)
        self.storage_page.pack_start(hdr, False, False, 0)

        tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tabs.set_margin_start(26); tabs.set_margin_end(26)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        cs = Gtk.Stack(); cs.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        cs.set_transition_duration(60); cs.set_vexpand(True)

        # Keep track of the current filter query and active listbox so
        # the search entry can filter live across all panels.
        self._storage_search_query = ""
        self._storage_listboxes    = {}   # name → Gtk.ListBox

        def _tab(label, panel, name):
            btn = Gtk.Button(label=label, relief=Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("tab-btn"); make_clickable(btn)
            def _act(b, n=name):
                self._storage_active_tab = n
                for t in tabs.get_children(): t.get_style_context().remove_class("tab-btn-active")
                b.get_style_context().add_class("tab-btn-active")
                cs.set_visible_child_name(n)
                self._storage_apply_filter()
            btn.connect("clicked", _act)
            tabs.pack_start(btn, False, False, 0)
            cs.add_named(panel, name); return btn

        tab_map = {}
        tab_map["rp"]     = _tab("Resource Packs",  self._storage_packs_panel(RESOURCE_DIR, "resource", "rp"), "rp")
        tab_map["bp"]     = _tab("Behaviour Packs",  self._storage_packs_panel(BEHAVIOUR_DIR, "behavior", "bp"), "bp")
        tab_map["worlds"] = _tab("Worlds",            self._storage_worlds_panel(),       "worlds")
        tab_map["deco"]   = _tab("Decorations",       self._storage_decorations_panel(),  "deco")
        tab_map["mods"]   = _tab("Mods",              self._storage_mods_panel(),         "mods")

        restore = active_tab if active_tab in tab_map else "rp"
        tab_map[restore].get_style_context().add_class("tab-btn-active")
        cs.set_visible_child_name(restore)
        self._storage_active_tab = restore

        # Wire search
        def _on_search(entry):
            self._storage_search_query = entry.get_text().strip().lower()
            self._storage_apply_filter()
        search.connect("search-changed", _on_search)

        self.storage_page.pack_start(tabs, False, False, 0)
        self.storage_page.pack_start(sep, False, False, 0)
        self.storage_page.pack_start(cs, True, True, 0)
        self.storage_page.show_all()

    def _storage_apply_filter(self):
        """Show/hide ListBox rows based on current search query."""
        q   = getattr(self, "_storage_search_query", "")
        tab = getattr(self, "_storage_active_tab", "rp")
        lb  = getattr(self, "_storage_listboxes", {}).get(tab)
        if lb is None: return
        for row in lb.get_children():
            if not q:
                row.show()
                continue
            # Try to find any label inside the row that matches
            found = False
            def _check(widget):
                nonlocal found
                if found: return
                if isinstance(widget, Gtk.Label):
                    txt = widget.get_text() or ""
                    if q in txt.lower():
                        found = True
                if hasattr(widget, "get_children"):
                    for ch in widget.get_children():
                        _check(ch)
            _check(row)
            if found: row.show()
            else:     row.hide()

    def _storage_packs_panel(self, packs_dir, ptype, tab_name="rp"):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        lb = Gtk.ListBox(); lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.get_style_context().add_class("card-list"); lb.set_hexpand(True)
        # Register so search can reach it
        if not hasattr(self, "_storage_listboxes"): self._storage_listboxes = {}
        self._storage_listboxes[tab_name] = lb
        packs = [(n, os.path.join(packs_dir, n)) for n in sorted(os.listdir(packs_dir))
                 if os.path.isdir(os.path.join(packs_dir, n))] if os.path.isdir(packs_dir) else []
        if not packs:
            em = Gtk.Label(label=f"No {ptype} packs installed.\nImport one from the Import page.")
            em.get_style_context().add_class("muted-label"); em.set_margin_top(40)
            em.set_justify(Gtk.Justification.CENTER); lb.add(em)
        else:
            for pname, ppath in packs:
                display = pname; desc = ""
                mf = os.path.join(ppath, "manifest.json")
                try:
                    d = json.load(open(mf)); hdr = d.get("header") or d
                    display = hdr.get("name") or hdr.get("displayName") or pname
                    desc = hdr.get("description") or d.get("description") or ""
                except Exception: pass
                rw = Gtk.EventBox()
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
                row.get_style_context().add_class("version-card")
                row.set_margin_top(4); row.set_margin_bottom(4)
                row.set_margin_start(14); row.set_margin_end(14)
                rw.add(row)
                icon_found = False
                for fn in ("pack_icon.png","pack.png","icon.png"):
                    fp = os.path.join(ppath, fn)
                    if os.path.exists(fp):
                        iw = Gtk.Image(); iw.set_size_request(52, 52)
                        iw.get_style_context().add_class("version-icon-box")
                        load_icon_async(fp, iw, 52, 52); row.pack_start(iw, False, False, 0)
                        icon_found = True; break
                if not icon_found:
                    fb = Gtk.Box(); fb.set_size_request(52,52)
                    fb.get_style_context().add_class("version-icon-box")
                    fb.pack_start(Gtk.Label(label="⚙" if ptype=="behavior" else "🎨"), True, True, 0)
                    row.pack_start(fb, False, False, 0)
                tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); tb.set_valign(Gtk.Align.CENTER)
                nl = Gtk.Label(label=display, xalign=0); nl.get_style_context().add_class("version-name")
                tb.pack_start(nl, False, False, 0)
                if desc:
                    dl = Gtk.Label(label=desc, xalign=0); dl.get_style_context().add_class("version-id")
                    dl.set_line_wrap(True); dl.set_max_width_chars(55); tb.pack_start(dl, False, False, 0)
                row.pack_start(tb, True, True, 0)
                db = styled_button("Delete","del-btn"); db.set_valign(Gtk.Align.CENTER)
                db.connect("clicked", lambda _, p=ppath: self._delete_modpack(p))
                row.pack_start(db, False, False, 0); lb.add(rw)
        panel.pack_start(self._scrolled(lb), True, True, 0); return panel

    def _storage_worlds_panel(self):
        """Worlds panel — FIX #5: larger world thumbnail (72×72)."""
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        lb = Gtk.ListBox(); lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.get_style_context().add_class("card-list"); lb.set_hexpand(True)
        if not hasattr(self, "_storage_listboxes"): self._storage_listboxes = {}
        self._storage_listboxes["worlds"] = lb
        worlds = [w for w in sorted(os.listdir(WORLDS_DIR))
                  if os.path.isdir(os.path.join(WORLDS_DIR, w))] if os.path.isdir(WORLDS_DIR) else []
        if not worlds:
            em = Gtk.Label(label="No worlds found.\nPlay Minecraft or import a .mcworld to see them here.")
            em.get_style_context().add_class("muted-label"); em.set_margin_top(40)
            em.set_justify(Gtk.Justification.CENTER); lb.add(em)
        else:
            for w in worlds:
                wpath = os.path.join(WORLDS_DIR, w); level_name = w
                lvl_txt = os.path.join(wpath, "levelname.txt")
                if os.path.exists(lvl_txt):
                    try: level_name = open(lvl_txt).read().strip() or w
                    except Exception: pass
                ldat = os.path.join(wpath, "level.dat")
                dat  = parse_level_dat(ldat) if os.path.exists(ldat) else {"seed":"—","gamemode":"—"}
                rw = Gtk.EventBox()
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
                row.get_style_context().add_class("version-card")
                row.set_margin_top(4); row.set_margin_bottom(4)
                row.set_margin_start(14); row.set_margin_end(14)
                rw.add(row)
                icon_path = os.path.join(wpath, "world_icon.jpeg")
                if not os.path.exists(icon_path): icon_path = os.path.join(wpath, "world_icon.png")
                WORLD_ICON = 72  # FIX #5 — was 48, now 72 so it's not chopped
                if os.path.exists(icon_path):
                    iw = Gtk.Image(); iw.set_size_request(WORLD_ICON, WORLD_ICON)
                    self._apply_inline_css(iw,
                        f"image {{ border-radius:8px; min-width:{WORLD_ICON}px; min-height:{WORLD_ICON}px; }}")
                    load_icon_async(icon_path, iw, WORLD_ICON, WORLD_ICON)
                    row.pack_start(iw, False, False, 0)
                else:
                    fb = Gtk.Box(); fb.set_size_request(WORLD_ICON, WORLD_ICON)
                    fb.get_style_context().add_class("version-icon-box")
                    fb.pack_start(Gtk.Label(label="🌍"), True, True, 0)
                    row.pack_start(fb, False, False, 0)
                tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3); tb.set_valign(Gtk.Align.CENTER)
                nl = Gtk.Label(label=level_name, xalign=0); nl.get_style_context().add_class("version-name")
                tb.pack_start(nl, False, False, 0)
                meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
                sl = Gtk.Label(xalign=0); sl.get_style_context().add_class("version-id")
                sl.set_markup(f"<span size='small'>🌱 Seed: <b>{dat['seed']}</b></span>")
                gl = Gtk.Label(xalign=0); gl.get_style_context().add_class("version-id")
                gl.set_markup(f"<span size='small'>⚔ <b>{dat['gamemode']}</b></span>")
                meta.pack_start(sl, False, False, 0); meta.pack_start(gl, False, False, 0)
                tb.pack_start(meta, False, False, 0); row.pack_start(tb, True, True, 0)
                db = styled_button("Delete","del-btn"); db.set_valign(Gtk.Align.CENTER)
                db.connect("clicked", lambda _, p=wpath: self._delete_world(p))
                row.pack_start(db, False, False, 0); lb.add(rw)
        panel.pack_start(self._scrolled(lb), True, True, 0); return panel

    def _storage_mods_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        lbl = Gtk.Label(label="Mod support coming soon.\nThis section is reserved for a future update.")
        lbl.get_style_context().add_class("muted-label")
        lbl.set_margin_top(60); lbl.set_justify(Gtk.Justification.CENTER)
        box.pack_start(lbl, False, False, 0); return box

    def _storage_decorations_panel(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True); sw.set_hexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.set_margin_start(14); content.set_margin_end(14)
        content.set_margin_top(10); content.set_margin_bottom(14)
        sw.add(content)
        def _deco_section(title, items, delete_cb, is_default_fn):
            lbl = Gtk.Label(label=title, xalign=0)
            lbl.get_style_context().add_class("settings-section")
            lbl.set_margin_top(10); content.pack_start(lbl, False, False, 0)
            if not items:
                em = Gtk.Label(label="None installed.", xalign=0)
                em.get_style_context().add_class("muted-label"); em.set_margin_start(4)
                content.pack_start(em, False, False, 0); return
            for fname, fpath in items:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.get_style_context().add_class("settings-row")
                icon_lbl = Gtk.Label(label="🖼" if title.startswith("B") else "🎨")
                row.pack_start(icon_lbl, False, False, 0)
                name_lbl = Gtk.Label(label=fname, xalign=0); name_lbl.set_hexpand(True)
                name_lbl.get_style_context().add_class("version-name")
                row.pack_start(name_lbl, True, True, 0)
                if is_default_fn(fname):
                    def_lbl = Gtk.Label(); def_lbl.set_markup("<b>DEFAULT</b>")
                    def_lbl.get_style_context().add_class("badge-default")
                    row.pack_start(def_lbl, False, False, 0)
                else:
                    db = styled_button("Delete", "del-btn"); db.set_valign(Gtk.Align.CENTER)
                    db.connect("clicked", lambda _, p=fpath: delete_cb(p))
                    row.pack_start(db, False, False, 0)
                content.pack_start(row, False, False, 0)
        bg_files = [(f, os.path.join(BG_DIR, f)) for f in sorted(os.listdir(BG_DIR))
                    if f.lower().endswith((".png", ".jpg", ".jpeg"))] if os.path.isdir(BG_DIR) else []
        cur_bg = load_settings().get("background", "home.png")
        def _del_bg(path):
            name = os.path.basename(path)
            if not self._confirm(f"Delete background '{name}'?"): return
            try: os.remove(path); self._notify("success", "Deleted", name)
            except Exception as e: self._notify("error", "Delete Failed", str(e))
            GLib.idle_add(lambda: self._rebuild_storage("deco")); GLib.idle_add(self._rebuild_home)
        _deco_section("BACKGROUNDS", bg_files, _del_bg, lambda f: f == cur_bg)
        theme_files = [(f, os.path.join(THEME_DIR, f)) for f in sorted(os.listdir(THEME_DIR))
                       if f.lower().endswith(".css")] if os.path.isdir(THEME_DIR) else []
        cur_th = load_settings().get("theme", "default.css")
        def _del_theme(path):
            name = os.path.basename(path)
            if not self._confirm(f"Delete theme '{name}'?"): return
            try: os.remove(path); self._notify("success", "Deleted", name)
            except Exception as e: self._notify("error", "Delete Failed", str(e))
            GLib.idle_add(lambda: self._rebuild_storage("deco")); GLib.idle_add(self._rebuild_settings)
        _deco_section("THEMES", theme_files, _del_theme, lambda f: f == cur_th or f == "default.css")
        outer.pack_start(sw, True, True, 0); return outer

    def _rebuild_modpacks(self): self._rebuild_storage()
    def _rebuild_worlds(self):   self._rebuild_storage()

    # ══════════════════════════════════════════════
    #  IMPORT PAGE
    # ══════════════════════════════════════════════
    def _create_import_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); box.set_hexpand(True); box.set_vexpand(True)
        box.pack_start(self._page_header("Import"), False, False, 0)
        card_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card_area.set_margin_start(26); card_area.set_margin_end(26); card_area.set_margin_top(8)
        def _card(title, subtitle, icon_name, cb):
            card = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
            card.get_style_context().add_class("import-card"); make_clickable(card)
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
            inner.set_margin_top(20); inner.set_margin_bottom(20)
            inner.set_margin_start(22); inner.set_margin_end(22)
            icon_path = os.path.join(ASSETS, "icons", icon_name)
            if os.path.exists(icon_path):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 36, 36, True)
                    inner.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
                except Exception: pass
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3); tb.set_valign(Gtk.Align.CENTER)
            t = Gtk.Label(label=title, xalign=0); t.get_style_context().add_class("version-name")
            s = Gtk.Label(label=subtitle, xalign=0); s.get_style_context().add_class("version-id")
            tb.pack_start(t, False, False, 0); tb.pack_start(s, False, False, 0)
            inner.pack_start(tb, True, True, 0)
            arr = Gtk.Label(label="›"); arr.get_style_context().add_class("arrow-label")
            inner.pack_start(arr, False, False, 0)
            card.add(inner); card.connect("clicked", cb); return card
        card_area.pack_start(_card("Import APK (x86)", "Add a Minecraft Bedrock version from an .apk file", "apk.png", self._import_apk), False, False, 0)
        card_area.pack_start(_card("Import Add-on", "Import .mcpack, .mcaddon, .mcworld or .mctemplate", "file.svg", self._import_addon), False, False, 0)
        card_area.pack_start(_card("Import Background", "Add a custom background image (.png, .jpg)", "importB.png", self._import_background), False, False, 0)
        card_area.pack_start(_card("Import Theme", "Add a custom CSS theme file", "importT.png", self._import_theme), False, False, 0)
        box.pack_start(card_area, False, False, 0)
        return box

    # ══════════════════════════════════════════════
    #  SETTINGS
    # ══════════════════════════════════════════════
    def _rebuild_settings(self):
        if not hasattr(self, "settings_page"): return
        self._clear(self.settings_page)
        settings = load_settings()
        self.settings_page.pack_start(self._page_header("Settings"), False, False, 0)
        tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tabs.set_margin_start(26); tabs.set_margin_end(26)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        cs = Gtk.Stack(); cs.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        cs.set_transition_duration(60); cs.set_vexpand(True)
        def _tab(label, panel, name):
            btn = Gtk.Button(label=label, relief=Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("tab-btn"); make_clickable(btn)
            def _act(b, n=name):
                for t in tabs.get_children(): t.get_style_context().remove_class("tab-btn-active")
                b.get_style_context().add_class("tab-btn-active")
                cs.set_visible_child_name(n)
            btn.connect("clicked", _act)
            tabs.pack_start(btn, False, False, 0)
            cs.add_named(panel, name); return btn
        def _sw(w):
            s = Gtk.ScrolledWindow()
            s.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            s.set_vexpand(True); s.set_hexpand(True); s.add(w); return s
        def _toggle(lbl_text, key, val):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.get_style_context().add_class("settings-row")
            cb2 = Gtk.CheckButton(label=lbl_text)
            cb2.get_style_context().add_class("settings-check")
            cb2.set_active(val); cb2.set_hexpand(True)
            cb2.connect("toggled", lambda w: self._on_toggle(key, w.get_active()))
            row.pack_start(cb2, True, True, 0); return row

        # Generic
        gen = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        gen.set_margin_start(26); gen.set_margin_end(26); gen.set_margin_bottom(26)
        gen.pack_start(self._section_lbl("GAME"), False, False, 0)
        gen.pack_start(_toggle("Allow beta versions",        "allow_beta",  settings.get("allow_beta",False)), False, False, 0)
        gen.pack_start(_toggle("Quit launcher after launch", "auto_quit",   settings.get("auto_quit",True)),   False, False, 0)
        gen.pack_start(self._section_lbl("STARTUP"), False, False, 0)
        gen.pack_start(_toggle("Random background on startup", "random_background", settings.get("random_background", False)), False, False, 0)
        gen.pack_start(_toggle("Show splash screen on startup", "splash_screen", settings.get("splash_screen", True)), False, False, 0)
        gen.pack_start(self._section_lbl("NOTIFICATIONS"), False, False, 0)
        gen.pack_start(_toggle("Show notification popups", "show_notifications", settings.get("show_notifications", True)), False, False, 0)
        gen.pack_start(self._section_lbl("ADVANCED"), False, False, 0)
        rb = styled_button("Reload Launcher","secondary-btn"); rb.set_halign(Gtk.Align.START)
        rb.connect("clicked", lambda *_: self._restart()); gen.pack_start(rb, False, False, 0)

        # Customize
        cust = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cust.set_margin_start(26); cust.set_margin_end(26); cust.set_margin_bottom(26)
        cust.pack_start(self._section_lbl("THEME"), False, False, 0)
        theme_files = self._list_theme_files()
        th_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        th_row.get_style_context().add_class("settings-row")
        th_lbl = Gtk.Label(label="Theme", xalign=0); th_lbl.set_hexpand(True)
        th_combo = Gtk.ComboBoxText(); th_combo.get_style_context().add_class("settings-combo")
        th_combo.set_size_request(200,-1); make_clickable(th_combo)
        for f in theme_files: th_combo.append_text(f)
        cur_th = settings.get("theme","")
        if cur_th in theme_files: th_combo.set_active(theme_files.index(cur_th))
        th_combo.connect("changed", self._on_theme_changed)
        th_row.pack_start(th_lbl, True, True, 0); th_row.pack_start(th_combo, False, False, 0)
        cust.pack_start(th_row, False, False, 0)
        cust.pack_start(self._section_lbl("BACKGROUND"), False, False, 0)
        bg_files = self._list_bg_files()
        bg_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bg_row.get_style_context().add_class("settings-row")
        bg_lbl = Gtk.Label(label="Background image", xalign=0); bg_lbl.set_hexpand(True)
        bg_combo = Gtk.ComboBoxText(); bg_combo.get_style_context().add_class("settings-combo")
        bg_combo.set_size_request(200,-1); make_clickable(bg_combo)
        for f in bg_files: bg_combo.append_text(f)
        cur_bg = settings.get("background","")
        if cur_bg in bg_files: bg_combo.set_active(bg_files.index(cur_bg))
        bg_combo.connect("changed", self._on_bg_changed)
        bg_row.pack_start(bg_lbl, True, True, 0); bg_row.pack_start(bg_combo, False, False, 0)
        cust.pack_start(bg_row, False, False, 0)

        # Client
        cl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cl_box.set_margin_start(26); cl_box.set_margin_end(26); cl_box.set_margin_bottom(26)
        cl_box.pack_start(self._section_lbl("CLIENT"), False, False, 0)
        cl_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        cl_row.get_style_context().add_class("settings-row")
        cl_cb = Gtk.CheckButton(label="Enable client mode")
        cl_cb.get_style_context().add_class("settings-check")
        cl_cb.set_active(settings.get("client_enabled", False)); cl_cb.set_hexpand(True)
        cl_note = Gtk.Label(label="(reserved for a future update)", xalign=0)
        cl_note.get_style_context().add_class("version-id")
        cl_cb.connect("toggled", lambda w: set_setting("client_enabled", w.get_active()))
        cl_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); cl_inner.set_hexpand(True)
        cl_inner.pack_start(cl_cb, False, False, 0); cl_inner.pack_start(cl_note, False, False, 0)
        cl_row.pack_start(cl_inner, True, True, 0); cl_box.pack_start(cl_row, False, False, 0)

        # About - redesigned
        about = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        about.set_halign(Gtk.Align.FILL)
        # Hero card
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        hero.get_style_context().add_class("about-hero")
        hero.set_margin_top(28); hero.set_margin_start(32); hero.set_margin_end(32)
        hero.set_margin_bottom(0)
        logo_app = os.path.join(ASSETS, "icons", "app.png")
        if os.path.exists(logo_app):
            try:
                pb_a = GdkPixbuf.Pixbuf.new_from_file_at_scale(logo_app, 64, 64, True)
                img_a = Gtk.Image.new_from_pixbuf(pb_a); img_a.set_halign(Gtk.Align.CENTER)
                hero.pack_start(img_a, False, False, 0)
            except Exception:
                logo_l = Gtk.Label(); logo_l.set_markup("<span size='xx-large'>⛏</span>")
                hero.pack_start(logo_l, False, False, 0)
        else:
            logo_l = Gtk.Label(); logo_l.set_markup("<span size='xx-large'>⛏</span>")
            hero.pack_start(logo_l, False, False, 0)
        title_l = Gtk.Label()
        title_l.set_markup(f"<span size='x-large' weight='heavy'>Bedrock Rock Launcher</span>")
        title_l.set_halign(Gtk.Align.CENTER)
        title_l.get_style_context().add_class("about-app-name")
        hero.pack_start(title_l, False, False, 0)
        ver_lbl = Gtk.Label()
        ver_lbl.set_markup(f"<span color='#3fcf8e' weight='bold'>v{LAUNCHER_VERSION}</span>  "
                           f"<span color='#484f58'>·  Unofficial  ·  Linux</span>")
        ver_lbl.set_halign(Gtk.Align.CENTER)
        hero.pack_start(ver_lbl, False, False, 0)
        about.pack_start(hero, False, False, 0)
        # Feature badges row
        feats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        feats_box.set_halign(Gtk.Align.CENTER)
        feats_box.set_margin_top(18); feats_box.set_margin_bottom(14)
        feats_box.set_margin_start(32); feats_box.set_margin_end(32)
        for feat in ("Ray", "Shouty00", "Mojang[Thanks to Them]"):
            fb = Gtk.Label(); fb.set_markup(f"<small>{feat}</small>")
            fb.get_style_context().add_class("about-feat-badge")
            feats_box.pack_start(fb, False, False, 0)
        about.pack_start(feats_box, False, False, 0)
        sep_a = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep_a.set_margin_start(32); sep_a.set_margin_end(32)
        about.pack_start(sep_a, False, False, 0)
        # Info grid
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_margin_top(16); info_box.set_margin_start(32); info_box.set_margin_end(32); info_box.set_margin_bottom(16)
        for key, val in (
            ("Runtime",   "Python 3  ·  GTK 3"),
            ("Platform",  "Linux"),
            ("Config",   "~/.config/mc-launcher"),
            ("Game Dir",  "~/mcpe_game"),
        ):
            r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); r.set_margin_bottom(2)
            kl = Gtk.Label(label=key, xalign=0); kl.set_size_request(90,-1)
            kl.get_style_context().add_class("settings-section")
            vl = Gtk.Label(label=val, xalign=0)
            vl.get_style_context().add_class("version-id")
            r.pack_start(kl, False, False, 0); r.pack_start(vl, True, True, 0)
            info_box.pack_start(r, False, False, 0)
        about.pack_start(info_box, False, False, 0)
        sep_a2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep_a2.set_margin_start(32); sep_a2.set_margin_end(32)
        about.pack_start(sep_a2, False, False, 0)
        # Footer
        footer = Gtk.Label(xalign=0.5, wrap=True)
        footer.set_markup(
            "<span size='small' color='#484f58'>"
            "Not affiliated with Mojang Studios or Microsoft.\n"
            "Minecraft® is a trademark of Mojang AB.\n"
            "Also all wallpaper are assets of Mojang and Microsoft\n"
            "[So i don't get sued :) ]"
            "</span>"
        )
        footer.set_margin_top(14); footer.set_margin_bottom(14); footer.set_margin_start(32); footer.set_margin_end(32)
        about.pack_start(footer, False, False, 0)

        t1 = _tab("Generic",   _sw(gen),    "generic")
        t1.get_style_context().add_class("tab-btn-active")
        _tab("Customize",  _sw(cust),                          "customize")
        _tab("Shortcuts",  _sw(self._build_shortcuts_panel()), "shortcuts")
        _tab("Client",     _sw(cl_box),                        "client")
        _tab("About",      _sw(about),                         "about")
        self.settings_page.pack_start(tabs, False, False, 0)
        self.settings_page.pack_start(sep,  False, False, 0)
        self.settings_page.pack_start(cs,   True,  True,  0)
        self.settings_page.show_all()

    # ══════════════════════════════════════════════
    #  PROFILE PAGE
    # ══════════════════════════════════════════════
    def _rebuild_profile(self):
        if not hasattr(self, "profile_page"): return
        self._clear(self.profile_page)
        profile = load_profile()
        display_name = profile.get("username","Player")
        self.profile_page.pack_start(self._page_header(display_name), False, False, 0)
        tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tabs.set_margin_start(26); tabs.set_margin_end(26)
        sep_below = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        content_stack = Gtk.Stack()
        content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        content_stack.set_transition_duration(60)
        def _make_tab(label, panel, name):
            btn = Gtk.Button(label=label, relief=Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("tab-btn"); make_clickable(btn)
            def _activate(b, n=name):
                for tb in tabs.get_children(): tb.get_style_context().remove_class("tab-btn-active")
                b.get_style_context().add_class("tab-btn-active")
                content_stack.set_visible_child_name(n)
            btn.connect("clicked", _activate)
            tabs.pack_start(btn, False, False, 0)
            content_stack.add_named(panel, name)
            return btn
        tab_ov = _make_tab("Overview", self._profile_overview_panel(profile, display_name), "overview")
        tab_ov.get_style_context().add_class("tab-btn-active")
        _make_tab("Skin",     self._profile_skin_panel(profile),     "skin")
        _make_tab("Game Log", self._profile_gamelog_panel(),          "gamelog")
        self.profile_page.pack_start(tabs, False, False, 0)
        self.profile_page.pack_start(sep_below, False, False, 0)
        self.profile_page.pack_start(content_stack, True, True, 0)
        self.profile_page.show_all()

    def _profile_overview_panel(self, profile, display_name):
        outer_sw = Gtk.ScrolledWindow()
        outer_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer_sw.set_vexpand(True); outer_sw.set_hexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_margin_start(26); content.set_margin_end(26); content.set_margin_bottom(26)
        outer_sw.add(content)
        av_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
        av_card.get_style_context().add_class("profile-header-card"); av_card.set_margin_top(14)
        # Avatar: custom picture or profile.png
        avatar_box = Gtk.Box(); avatar_box.set_size_request(80, 80)
        avatar_box.set_halign(Gtk.Align.CENTER); avatar_box.set_valign(Gtk.Align.CENTER)
        pic_path = profile.get("profile_picture")
        loaded_pic = False
        if pic_path and os.path.exists(pic_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(pic_path, 80, 80, True)
                img = Gtk.Image.new_from_pixbuf(pb)
                self._apply_inline_css(avatar_box,
                    ".av-pic-lg { border-radius:40px; border:2px solid rgba(255,255,255,0.12); }")
                avatar_box.get_style_context().add_class("av-pic-lg")
                avatar_box.pack_start(img, True, True, 0); loaded_pic = True
            except Exception: pass
        if not loaded_pic:
            svg_path = os.path.join(ASSETS, "icons", "profile.png")
            if os.path.exists(svg_path):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(svg_path, 80, 80, True)
                    img = Gtk.Image.new_from_pixbuf(pb)
                    self._apply_inline_css(avatar_box,
                        ".av-svg-lg { border-radius:40px; background:rgba(63,207,142,0.10); padding:8px; }")
                    avatar_box.get_style_context().add_class("av-svg-lg")
                    avatar_box.pack_start(img, True, True, 0); loaded_pic = True
                except Exception: pass
        if not loaded_pic:
            dot = Gtk.Box(); dot.set_size_request(80, 80)
            self._apply_inline_css(dot,
                ".av-fb-lg { background:#3fcf8e; border-radius:40px; min-width:80px; min-height:80px; }")
            dot.get_style_context().add_class("av-fb-lg")
            init_lbl = Gtk.Label()
            init_lbl.set_markup(f"<span weight='bold' color='#fff' size='xx-large'>{(display_name or 'P')[0].upper()}</span>")
            init_lbl.set_halign(Gtk.Align.CENTER); init_lbl.set_valign(Gtk.Align.CENTER)
            dot.pack_start(init_lbl, True, True, 0)
            avatar_box.pack_start(dot, True, True, 0)
        av_card.pack_start(avatar_box, False, False, 0)
        nc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5); nc.set_valign(Gtk.Align.CENTER)
        name_big = Gtk.Label(label=display_name or "Player", xalign=0)
        name_big.get_style_context().add_class("page-title")
        nc.pack_start(name_big, False, False, 0)
        bio = profile.get("bio","")
        bl = Gtk.Label(label=bio if bio else "No bio set.", xalign=0)
        bl.get_style_context().add_class("version-id")
        nc.pack_start(bl, False, False, 0)
        av_card.pack_start(nc, True, True, 0)
        edit_btn = styled_button("Edit Profile","secondary-btn"); edit_btn.set_valign(Gtk.Align.CENTER)
        edit_btn.connect("clicked", lambda *_: self._edit_profile_dialog())
        av_card.pack_start(edit_btn, False, False, 0)
        content.pack_start(av_card, False, False, 0)
        content.pack_start(self._section_lbl("STATISTICS"), False, False, 0)
        pt_data = load_playtime()
        total_pt   = sum(v for v in pt_data.values() if isinstance(v,(int,float)))
        session_pt = time.time() - self._session_start
        launches   = profile.get("launches", len(pt_data))
        stats_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        stats_row.get_style_context().add_class("settings-row")
        def _stat_box(val, lbl):
            b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2); b.set_hexpand(True)
            vl = Gtk.Label(label=str(val)); vl.get_style_context().add_class("home-stat-value")
            ll = Gtk.Label(label=lbl); ll.get_style_context().add_class("home-stat-label")
            b.pack_start(vl, False, False, 0); b.pack_start(ll, False, False, 0)
            return b
        stats_row.pack_start(_stat_box(format_playtime(total_pt),  "PLAY TIME"),  True, True, 0)
        stats_row.pack_start(_stat_box(format_playtime(session_pt),"THIS SESSION"), True, True, 0)
        stats_row.pack_start(_stat_box(launches, "LAUNCHES"), True, True, 0)
        content.pack_start(stats_row, False, False, 0)
        if pt_data:
            content.pack_start(self._section_lbl("PER VERSION"), False, False, 0)
            max_pt = max((v for v in pt_data.values() if isinstance(v,(int,float))), default=1)
            for vid, secs in sorted(pt_data.items(), key=lambda x: -x[1])[:8]:
                if not isinstance(secs,(int,float)): continue
                vc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                vc.get_style_context().add_class("settings-row")
                top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                vl = Gtk.Label(label=vid, xalign=0); vl.get_style_context().add_class("version-name"); vl.set_hexpand(True)
                tl = Gtk.Label(label=format_playtime(secs), xalign=1); tl.get_style_context().add_class("home-stat-value")
                top.pack_start(vl, True, True, 0); top.pack_start(tl, False, False, 0)
                pb3 = Gtk.ProgressBar(); pb3.set_fraction(min(1.0, secs/max(1, max_pt)))
                pb3.get_style_context().add_class("version-bar")
                vc.pack_start(top, False, False, 0); vc.pack_start(pb3, False, False, 0)
                content.pack_start(vc, False, False, 0)
        return outer_sw

    def _profile_skin_panel(self, profile):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True); sw.set_hexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_start(26); content.set_margin_end(26)
        content.set_margin_top(14); content.set_margin_bottom(26)
        sw.add(content)
        skin_path = [find_active_skin()]
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=28)
        card.get_style_context().add_class("profile-header-card"); card.set_margin_top(8)
        viewer = SkinView3D()
        viewer.set_halign(Gtk.Align.CENTER); viewer.set_valign(Gtk.Align.CENTER)
        viewer_box = Gtk.Box()
        viewer_box.get_style_context().add_class("skin-preview-box")
        viewer_box.set_halign(Gtk.Align.CENTER); viewer_box.set_valign(Gtk.Align.CENTER)
        viewer_box.pack_start(viewer, True, True, 0)
        if skin_path[0]: viewer.load_skin(skin_path[0])
        card.pack_start(viewer_box, False, False, 0)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); right.set_valign(Gtk.Align.CENTER)
        name_lbl = Gtk.Label(xalign=0)
        sp0 = skin_path[0]
        if sp0:
            name_lbl.set_markup(f"<b>Active Skin</b>\n<span size='small' color='#8b949e'>{os.path.basename(sp0)}</span>")
        else:
            name_lbl.set_markup("<b>No skin found</b>\n<span size='small' color='#8b949e'>Import a 64×64 PNG to get started</span>")
        name_lbl.get_style_context().add_class("version-name")
        right.pack_start(name_lbl, False, False, 0)
        def _change(*_):
            fd = Gtk.FileChooserDialog(title="Select Skin PNG", parent=self, action=Gtk.FileChooserAction.OPEN)
            fd.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
            ff = Gtk.FileFilter(); ff.set_name("PNG Images"); ff.add_pattern("*.png"); fd.add_filter(ff)
            if fd.run() != Gtk.ResponseType.OK: fd.destroy(); return
            src = fd.get_filename(); fd.destroy()
            if not src: return
            try:
                GdkPixbuf.Pixbuf.new_from_file(src)
                dst = os.path.join(CUSTOM_SKINS, os.path.basename(src))
                shutil.copy2(src, dst); skin_path[0] = dst
                name_lbl.set_markup(f"<b>Active Skin</b>\n<span size='small' color='#8b949e'>{os.path.basename(dst)}</span>")
                viewer.load_skin(dst)
                self._notify("success", "Skin Changed", os.path.basename(dst))
            except Exception as e:
                self._notify("error", "Skin Import Failed", str(e))
        change_btn = styled_button("🎨  Change Skin", "small-play")
        change_btn.connect("clicked", _change); right.pack_start(change_btn, False, False, 0)
        def _open_folder(*_):
            try: subprocess.Popen(["xdg-open", CUSTOM_SKINS])
            except Exception: pass
        folder_btn = styled_button("📁  Open Skins Folder", "secondary-btn")
        folder_btn.connect("clicked", _open_folder); right.pack_start(folder_btn, False, False, 0)
        card.pack_start(right, True, True, 0)
        content.pack_start(card, False, False, 0)
        note = Gtk.Label(xalign=0, wrap=True)
        note.set_markup(f"<span size='small' color='#484f58'>Skins folder: {CUSTOM_SKINS}\nMost-recently-modified PNG is shown as your active skin.</span>")
        note.get_style_context().add_class("version-id")
        content.pack_start(note, False, False, 0)
        return sw

    # ══════════════════════════════════════════════
    #  GAME LOG — FIX #8: color-coded, filterable, searchable
    # ══════════════════════════════════════════════
    def _profile_gamelog_panel(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_start(0); outer.set_margin_end(0)
        outer.set_margin_top(0); outer.set_margin_bottom(0)

        # ── Toolbar ──────────────────────────────────────────────
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(26); toolbar.set_margin_end(26)
        toolbar.set_margin_top(14); toolbar.set_margin_bottom(8)

        # Search entry
        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Search log…")
        search_entry.set_size_request(220, -1)
        toolbar.pack_start(search_entry, False, False, 0)

        # Filter buttons
        filter_state = {"level": "ALL"}
        filter_btns = {}
        filters_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for lvl, color in (("ALL","#8b949e"),("ERROR","#f85149"),("WARN","#f0c000"),("INFO","#8b949e"),("TRACE","#484f58")):
            fb = Gtk.Button(label=lvl)
            fb.get_style_context().add_class("mini-btn")
            if lvl == "ALL":
                fb.get_style_context().add_class("tab-btn-active")
            make_clickable(fb)
            filter_btns[lvl] = fb
            filters_box.pack_start(fb, False, False, 0)
        toolbar.pack_start(filters_box, False, False, 0)

        spacer_tb = Gtk.Box(); spacer_tb.set_hexpand(True)
        toolbar.pack_start(spacer_tb, True, True, 0)

        # Line count label
        line_count_lbl = Gtk.Label(label="")
        line_count_lbl.get_style_context().add_class("version-id")
        toolbar.pack_start(line_count_lbl, False, False, 0)

        clr_btn = styled_button("Clear", "mini-btn")
        toolbar.pack_start(clr_btn, False, False, 0)

        refresh_btn = styled_button("↻ Refresh", "mini-btn")
        toolbar.pack_start(refresh_btn, False, False, 0)

        outer.pack_start(toolbar, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        outer.pack_start(sep, False, False, 0)

        # ── Log view ─────────────────────────────────────────────
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True); sw.set_hexpand(True)
        sw.set_margin_start(14); sw.set_margin_end(14); sw.set_margin_top(8); sw.set_margin_bottom(14)

        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        tv.get_style_context().add_class("console")
        buf = tv.get_buffer()

        # Build tag table for colored lines
        tag_table = buf.get_tag_table()
        tags = {}
        for name, color in LOG_COLORS.items():
            tag = buf.create_tag(name, foreground=color)
            tags[name] = tag

        sw.add(tv)
        outer.pack_start(sw, True, True, 0)

        # ── Log rendering ─────────────────────────────────────────
        all_lines = []   # cache of raw lines

        def _load_lines():
            nonlocal all_lines
            raw = read_gamelog()
            all_lines = raw.splitlines() if raw else []

        def _render(search="", level_filter="ALL"):
            buf.set_text("")
            visible = 0
            for line in all_lines:
                cls = classify_log_line(line)
                if level_filter != "ALL" and cls.upper() != level_filter.lower() and level_filter != cls.upper():
                    # mapping
                    cls_up = cls.upper()
                    if level_filter not in ("ALL", cls_up):
                        if not (level_filter == "WARN" and cls == "warn"):
                            # stricter check
                            pass
                    # simplified: just check
                    lf = level_filter.lower()
                    if lf != "all" and cls != lf and not (lf == "warn" and cls == "warn") and not (lf == "error" and cls == "error"):
                        if level_filter != "ALL" and cls.upper() != level_filter:
                            continue
                if search and search.lower() not in line.lower():
                    continue
                it = buf.get_end_iter()
                buf.insert_with_tags(it, line + "\n", tags.get(cls, tags["default"]))
                visible += 1
            line_count_lbl.set_text(f"{visible} / {len(all_lines)} lines")
            # Scroll to bottom
            GLib.idle_add(_scroll_bottom)

        def _scroll_bottom():
            adj = sw.get_vadjustment()
            adj.set_value(adj.get_upper())

        def _filter_render():
            _render(search_entry.get_text(), filter_state["level"])

        # Connect filter buttons
        def _make_filter_cb(lvl):
            def _cb(btn):
                filter_state["level"] = lvl
                for fl, fb2 in filter_btns.items():
                    ctx = fb2.get_style_context()
                    ctx.remove_class("tab-btn-active")
                    if fl == lvl: ctx.add_class("tab-btn-active")
                _filter_render()
            return _cb
        for lvl2 in filter_btns:
            filter_btns[lvl2].connect("clicked", _make_filter_cb(lvl2))

        search_entry.connect("search-changed", lambda *_: _filter_render())

        def _clear_log(*_):
            try: open(GAMELOG_FILE, "w").close()
            except Exception: pass
            all_lines.clear()
            buf.set_text("")
            line_count_lbl.set_text("0 / 0 lines")
        clr_btn.connect("clicked", _clear_log)

        def _refresh(*_):
            _load_lines(); _filter_render()
        refresh_btn.connect("clicked", _refresh)

        # Initial load
        _load_lines()
        _filter_render()

        # Auto-scroll to bottom initially
        GLib.idle_add(_scroll_bottom)

        return outer

    # ══════════════════════════════════════════════
    #  LAUNCH
    # ══════════════════════════════════════════════
    def _launch_version(self, vid):
        settings = load_settings(); vdir = os.path.join(GAME_DIR, vid)
        lib_path = os.path.join(vdir, "lib", "x86_64")
        cmd = [
            "flatpak", "run",
            "--command=mcpelauncher-client",
            "--filesystem=home",
            f"--env=LD_LIBRARY_PATH={lib_path}",
            "io.mrarm.mcpelauncher",
            "-dg", vdir, "-dd", str(COM_MOJANG),
            "-m", str(MOD_DIR)
        ]
        launch_time = time.time()
        append_gamelog(f"Launching version {vid}")
        p = load_profile(); p["launches"] = p.get("launches",0) + 1; save_profile(p)
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self._notify("info", "Launching", f"Minecraft {vid}")
            if settings.get("auto_quit", True):
                append_gamelog(f"Launcher exiting (auto_quit)")
                Gtk.main_quit(); return
            def _track():
                try:
                    for line in iter(proc.stdout.readline, ""):
                        if line: append_gamelog(line.rstrip())
                except Exception: pass
                proc.wait()
                elapsed = time.time() - launch_time
                pt = load_playtime(); pt[vid] = pt.get(vid, 0) + elapsed; save_playtime(pt)
                append_gamelog(f"Session ended: {format_playtime(elapsed)}")
            threading.Thread(target=_track, daemon=True).start()
        except Exception as e:
            append_gamelog(f"ERROR launching {vid}: {e}")
            self._notify("error", "Launch Failed", str(e))

    # ══════════════════════════════════════════════
    #  NOTIFICATIONS
    # ══════════════════════════════════════════════
    def _notify(self, ntype, title, body):
        if not load_settings().get("show_notifications", True): return
        n = {"id": str(time.time()), "type": ntype, "title": title, "body": body, "timestamp": time.time()}
        ns = load_notifications(); ns.append(n); save_notifications(ns)
        GLib.idle_add(self._show_notif_popup, n)

    def _show_pending_notifications(self):
        if not load_settings().get("show_notifications", True): return
        for i, n in enumerate(load_notifications()[:3]):
            GLib.timeout_add(400 * (i + 1), lambda nn=n: self._show_notif_popup(nn))

    def _show_notif_popup(self, notification):
        color, icon = NOTIF_COLORS.get(notification["type"], ("#3fcf8e", "ℹ"))
        # Play sound
        if load_settings().get("show_notifications", True):
            _play_notif_sound(notification["type"])

        # ── Build the notification widget ────────────────────────
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        accent_bar = Gtk.Box()
        accent_bar.set_size_request(4, -1)
        self._apply_inline_css(accent_bar,
            f".notif-accent {{ background-color:{color}; border-radius:4px 0 0 4px; min-width:4px; }}")
        accent_bar.get_style_context().add_class("notif-accent")
        outer.pack_start(accent_bar, False, False, 0)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        inner.set_margin_top(14); inner.set_margin_bottom(14)
        inner.set_margin_start(16); inner.set_margin_end(12)
        ic = Gtk.Label()
        ic.set_markup(f"<span size='large'>{icon}</span>"); ic.set_valign(Gtk.Align.CENTER)
        inner.pack_start(ic, False, False, 0)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        tl = Gtk.Label(xalign=0); tl.set_markup(f"<b>{notification['title']}</b>")
        tl.get_style_context().add_class("notif-title")
        bl = Gtk.Label(label=notification["body"], xalign=0)
        bl.set_line_wrap(True); bl.set_max_width_chars(52)
        bl.get_style_context().add_class("notif-body")
        txt.pack_start(tl, False, False, 0); txt.pack_start(bl, False, False, 0)
        inner.pack_start(txt, True, True, 0)
        close_btn = Gtk.Button(label="✕"); close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.get_style_context().add_class("notif-close"); make_clickable(close_btn)
        close_btn.set_valign(Gtk.Align.CENTER)
        inner.pack_start(close_btn, False, False, 0)
        outer.pack_start(inner, True, True, 0)

        fr = Gtk.Frame(); fr.add(outer)
        fr.set_halign(Gtk.Align.FILL); fr.set_valign(Gtk.Align.START)
        fr.get_style_context().add_class("notif-frame")
        notif_bg = {
            "error":   "#883322",
            "success": "#008F46",
            "warning": "#745E1E",
        }.get(notification["type"], "#1a2235")
        self._apply_inline_css(fr,
            f".notif-frame {{ background-color:{notif_bg}; "
            f"border-radius:8px; border:1px solid rgba(255,255,255,0.06); }}")

        # ── Animate in: slide down from top + fade in ─────────────
        # Use a wrapper box so we can control the top margin for slide
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.pack_start(fr, False, False, 0)

        # Start hidden above: negative top margin, fully transparent
        _SLIDE_PX   = 28      # pixels to slide
        _ANIM_MS    = 12      # ms per tick  (~60 fps)
        _ANIM_STEPS = 14      # total ticks for slide-in

        fr.set_margin_top(-_SLIDE_PX)
        fr.set_opacity(0.0)

        self._notif_vbox.pack_start(wrapper, False, False, 0)
        self._overlay.show_all()

        anim_state = {"step": 0, "dismissing": False}

        def _ease_out(t):
            return 1.0 - (1.0 - t) ** 3   # cubic ease-out

        def _anim_in():
            anim_state["step"] += 1
            t = min(1.0, anim_state["step"] / _ANIM_STEPS)
            e = _ease_out(t)
            fr.set_margin_top(int(-_SLIDE_PX * (1.0 - e)))
            fr.set_opacity(e)
            if t < 1.0: return True   # keep ticking
            fr.set_margin_top(0); fr.set_opacity(1.0)
            return False              # done

        GLib.timeout_add(_ANIM_MS, _anim_in)

        # ── Animate out: fade + slide up, then remove ─────────────
        def _dismiss_animated(*_):
            if anim_state["dismissing"]: return False
            anim_state["dismissing"] = True
            nid = notification.get("id")
            if nid:
                save_notifications(
                    [n for n in load_notifications() if n.get("id") != nid])
            out_steps = [0]
            def _anim_out():
                out_steps[0] += 1
                t = min(1.0, out_steps[0] / _ANIM_STEPS)
                e = _ease_out(t)
                fr.set_opacity(1.0 - e)
                fr.set_margin_top(int(-_SLIDE_PX * e))
                if t < 1.0: return True
                try: self._notif_vbox.remove(wrapper)
                except Exception: pass
                return False
            GLib.timeout_add(_ANIM_MS, _anim_out)
            return False

        close_btn.connect("clicked", _dismiss_animated)
        if notification["type"] in ("info", "success") and NOTIF_AUTODISMISS_SECS > 0:
            GLib.timeout_add_seconds(NOTIF_AUTODISMISS_SECS, _dismiss_animated)

    # ══════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════
    def _confirm(self, msg):
        dlg = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.YES_NO, text=msg)
        r = dlg.run() == Gtk.ResponseType.YES; dlg.destroy(); return r

    def _list_bg_files(self):
        try: return [f for f in sorted(os.listdir(BG_DIR)) if f.lower().endswith((".png",".jpg",".jpeg"))]
        except Exception: return []

    def _list_theme_files(self):
        try: return [f for f in sorted(os.listdir(THEME_DIR)) if f.lower().endswith(".css")]
        except Exception: return []

    def _on_toggle(self, key, val):
        set_setting(key, val); GLib.idle_add(self._rebuild_home)

    def _on_bg_changed(self, combo):
        files = self._list_bg_files(); idx = combo.get_active()
        if 0 <= idx < len(files): set_setting("background", files[idx]); GLib.idle_add(self._rebuild_home)

    def _on_theme_changed(self, combo):
        files = self._list_theme_files(); idx = combo.get_active()
        if 0 <= idx < len(files):
            set_setting("theme", files[idx]); self._load_css()
            # refresh theme art
            if hasattr(self, "_theme_art"):
                self._theme_art.set_theme(files[idx])
            GLib.idle_add(self._rebuild_home)

    def _set_default_version(self, vid):
        set_setting("default_version", vid)
        self._notify("success","Default Set",f"{vid} is now default")
        GLib.idle_add(self._rebuild_versions); GLib.idle_add(self._rebuild_home)

    def _edit_version(self, vid):
        vdir = os.path.join(GAME_DIR, vid); ip = os.path.join(vdir,"version_info.json")
        if not os.path.exists(ip): return
        try: info = json.load(open(ip))
        except Exception: info = {"display_name":vid,"version_id":vid,"beta":False}
        updated = self._version_info_dialog(info.get("display_name",vid), info.get("version_id",vid))
        if not updated: return
        new_vid = updated["version_id"]; new_dir = vdir
        if new_vid != vid:
            new_dir = os.path.join(GAME_DIR, new_vid)
            try: os.rename(vdir, new_dir)
            except Exception as e: self._notify("error","Rename Failed",str(e)); return
        try:
            with open(os.path.join(new_dir,"version_info.json"),"w") as f: json.dump(updated,f,indent=2)
            self._notify("success","Updated",updated["display_name"])
        except Exception as e: self._notify("error","Save Failed",str(e)); return
        s = load_settings()
        if s.get("default_version")==vid: set_setting("default_version",new_vid)
        GLib.idle_add(self._rebuild_versions); GLib.idle_add(self._rebuild_home)

    def _delete_version(self, vid):
        if not self._confirm(f"Delete version '{vid}' and all its files?"): return
        try: shutil.rmtree(os.path.join(GAME_DIR,vid)); self._notify("success","Deleted",f"Version {vid} deleted")
        except Exception as e: self._notify("error","Delete Failed",str(e))
        s = load_settings()
        if s.get("default_version")==vid: set_setting("default_version",None)
        GLib.idle_add(self._rebuild_versions); GLib.idle_add(self._rebuild_home)

    def _version_info_dialog(self, dname="", did=""):
        dlg = Gtk.Dialog(title="Version Info",parent=self,flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,Gtk.STOCK_OK,Gtk.ResponseType.OK)
        dlg.set_default_size(360,180)
        grid = Gtk.Grid(column_spacing=10,row_spacing=10)
        grid.set_margin_top(14); grid.set_margin_bottom(14); grid.set_margin_start(14); grid.set_margin_end(14)
        dlg.get_content_area().add(grid)
        en = Gtk.Entry(); en.set_text(dname); ei = Gtk.Entry(); ei.set_text(did)
        eb = Gtk.CheckButton(label="Beta version")
        grid.attach(Gtk.Label(label="Display Name:",xalign=1),0,0,1,1); grid.attach(en,1,0,1,1)
        grid.attach(Gtk.Label(label="Version ID:",  xalign=1),0,1,1,1); grid.attach(ei,1,1,1,1)
        grid.attach(eb,0,2,2,1); dlg.show_all(); result=None
        if dlg.run()==Gtk.ResponseType.OK:
            result={"display_name":en.get_text().strip() or dname,"version_id":ei.get_text().strip() or did,"beta":eb.get_active()}
        dlg.destroy(); return result

    def _create_server_dialog(self, *_):
        dlg = Gtk.Dialog(title="New Server",parent=self,flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,Gtk.STOCK_OK,Gtk.ResponseType.OK)
        dlg.set_default_size(500,220)
        box = dlg.get_content_area(); box.set_margin_top(14); box.set_margin_bottom(14); box.set_margin_start(16); box.set_margin_end(16)
        ne = Gtk.Entry(); ne.set_placeholder_text("My Bedrock Server")
        box.pack_start(Gtk.Label(label="Server Name:",xalign=0),False,False,4); box.pack_start(ne,False,False,4)
        zr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=6)
        ze = Gtk.Entry(); ze.set_placeholder_text("Select ZIP…"); ze.set_editable(False); ze.set_hexpand(True)
        br3 = styled_button("Browse…","mini-btn")
        def _pick(*_):
            fd=Gtk.FileChooserDialog(title="Select ZIP",parent=dlg,action=Gtk.FileChooserAction.OPEN)
            fd.add_buttons(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,Gtk.STOCK_OPEN,Gtk.ResponseType.OK)
            ff=Gtk.FileFilter(); ff.set_name("ZIP"); ff.add_pattern("*.zip"); fd.add_filter(ff)
            if fd.run()==Gtk.ResponseType.OK: ze.set_text(fd.get_filename()); fd.destroy()
        br3.connect("clicked",_pick); zr.pack_start(ze,True,True,0); zr.pack_start(br3,False,False,0)
        box.pack_start(Gtk.Label(label="Bedrock Server ZIP:",xalign=0),False,False,8); box.pack_start(zr,False,False,4)
        dlg.show_all()
        if dlg.run()!=Gtk.ResponseType.OK: dlg.destroy(); return
        sname=ne.get_text().strip(); zpath=ze.get_text().strip(); dlg.destroy()
        if not sname: self._notify("error","Invalid","Enter a server name"); return
        if not zpath or not os.path.exists(zpath): self._notify("error","Invalid","Select a valid ZIP"); return
        spath=os.path.join(SERVER_DIR,sname)
        if os.path.exists(spath): self._notify("error","Exists","Server name already taken"); return
        pw,pb4=show_progress_window(self,"Creating Server",f"Extracting {sname}…")
        GLib.timeout_add(120,lambda:pw.get_visible() and (pb4.pulse() or True))
        def _work():
            try:
                os.makedirs(spath,exist_ok=True); flatten_zip(zpath,spath,pb4.set_fraction)
                ep=os.path.join(spath,"bedrock_server")
                if os.path.exists(ep): os.chmod(ep,0o755)
                GLib.idle_add(self._notify,"success","Server Created",sname)
            except zipfile.BadZipFile: GLib.idle_add(self._notify,"error","Failed","Not a valid ZIP")
            except Exception as e: GLib.idle_add(self._notify,"error","Failed",str(e))
            finally: GLib.idle_add(pw.destroy); GLib.idle_add(self._rebuild_servers)
        threading.Thread(target=_work,daemon=True).start()

    def _delete_server(self, spath):
        name=os.path.basename(spath)
        if not self._confirm(f"Delete server '{name}'?"): return
        try: shutil.rmtree(spath); self._notify("success","Deleted",f"Server {name} deleted")
        except Exception as e: self._notify("error","Delete Failed",str(e))
        GLib.idle_add(self._rebuild_servers)

    def _import_apk(self, *_):
        fd=Gtk.FileChooserDialog(title="Select APK",parent=self,action=Gtk.FileChooserAction.OPEN)
        fd.add_buttons(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,Gtk.STOCK_OPEN,Gtk.ResponseType.OK)
        ff=Gtk.FileFilter(); ff.set_name("APK"); ff.add_pattern("*.apk"); fd.add_filter(ff)
        if fd.run()!=Gtk.ResponseType.OK: fd.destroy(); return
        apk_path=fd.get_filename(); fd.destroy()
        base=os.path.splitext(os.path.basename(apk_path))[0]
        info=self._version_info_dialog(base,base)
        if not info: return
        td=os.path.join(GAME_DIR,info["version_id"]); os.makedirs(td,exist_ok=True)
        with open(os.path.join(td,"version_info.json"),"w") as f: json.dump(info,f,indent=2)
        pw,pb5=show_progress_window(self,"Importing APK",f"Extracting {info['display_name']}…")
        def _work():
            try: flatten_zip(apk_path,td,pb5.set_fraction); GLib.idle_add(self._notify,"success","APK Imported",info["display_name"])
            except zipfile.BadZipFile: GLib.idle_add(self._notify,"error","Failed","Not a valid APK")
            except Exception as e: GLib.idle_add(self._notify,"error","Failed",str(e))
            finally: GLib.idle_add(pw.destroy); GLib.idle_add(self._rebuild_versions); GLib.idle_add(self._rebuild_home)
        threading.Thread(target=_work,daemon=True).start()

    def _import_addon(self, *_):
        type_dlg = Gtk.Dialog(title="What are you importing?", parent=self, flags=0)
        type_dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Choose File", Gtk.ResponseType.OK)
        type_dlg.set_default_size(380, 290)
        box = type_dlg.get_content_area()
        box.set_margin_top(14); box.set_margin_bottom(8); box.set_margin_start(20); box.set_margin_end(20)
        lbl = Gtk.Label(label="Select the type you want to import:", xalign=0)
        lbl.get_style_context().add_class("settings-section"); lbl.set_margin_bottom(10)
        box.pack_start(lbl, False, False, 0)
        import_types = [
            ("mcpack",     ".mcpack  — Single pack (auto-detects BP/RP)"),
            ("mcaddon",    ".mcaddon  — Addon bundle (auto-splits BP + RP)"),
            ("mcworld",    ".mcworld  — World save"),
            ("mctemplate", ".mctemplate  — World template"),
            ("zip",        ".zip  — Plain ZIP archive"),
            ("any",        "Any of the above"),
        ]
        radios = []; first_rb = None
        for val, desc in import_types:
            rb = Gtk.RadioButton.new_with_label_from_widget(first_rb, desc)
            if first_rb is None: first_rb = rb
            radios.append((val, rb)); box.pack_start(rb, False, False, 2)
        type_dlg.show_all()
        if type_dlg.run() != Gtk.ResponseType.OK: type_dlg.destroy(); return
        chosen = next((v for v, r in radios if r.get_active()), "any")
        type_dlg.destroy()
        fd = Gtk.FileChooserDialog(title="Select File", parent=self, action=Gtk.FileChooserAction.OPEN)
        fd.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        ff = Gtk.FileFilter()
        if   chosen == "mcpack":     ff.set_name(".mcpack");     ff.add_pattern("*.mcpack")
        elif chosen == "mcaddon":    ff.set_name(".mcaddon");    ff.add_pattern("*.mcaddon")
        elif chosen == "mcworld":    ff.set_name(".mcworld");    ff.add_pattern("*.mcworld")
        elif chosen == "mctemplate": ff.set_name(".mctemplate"); ff.add_pattern("*.mctemplate")
        elif chosen == "zip":        ff.set_name(".zip");        ff.add_pattern("*.zip")
        else:
            ff.set_name("Minecraft Files")
            for p in ("*.mcpack","*.mcaddon","*.mcworld","*.mctemplate","*.zip"): ff.add_pattern(p)
        fd.add_filter(ff)
        if fd.run() != Gtk.ResponseType.OK: fd.destroy(); return
        file_path = fd.get_filename(); fd.destroy()
        if not file_path: return
        ext = os.path.splitext(file_path)[1].lower()
        name = os.path.splitext(os.path.basename(file_path))[0]
        if ext == ".mcaddon" or chosen == "mcaddon":
            pw, pb6 = show_progress_window(self, "Importing Addon", f"Splitting {name}…")
            GLib.timeout_add(120, lambda: pw.get_visible() and (pb6.pulse() or True))
            def _do_addon():
                results = import_mcaddon(file_path, pb6.set_fraction)
                if results:
                    parts = ", ".join(f"{n} ({t})" for n, t in results)
                    GLib.idle_add(self._notify, "success", "Addon Imported", parts)
                else:
                    GLib.idle_add(self._notify, "error", "Import Failed", "No valid packs found in .mcaddon")
                GLib.idle_add(pw.destroy); GLib.idle_add(self._rebuild_storage)
            threading.Thread(target=_do_addon, daemon=True).start()
        elif ext in (".mcworld", ".mctemplate") or chosen in ("mcworld","mctemplate"):
            tgt = os.path.join(WORLDS_DIR, name); n2 = 1
            while os.path.exists(tgt): tgt = os.path.join(WORLDS_DIR, f"{name}_{n2}"); n2 += 1
            os.makedirs(tgt, exist_ok=True)
            pw, pb6 = show_progress_window(self, "Importing World", f"Extracting {name}…")
            GLib.timeout_add(120, lambda: pw.get_visible() and (pb6.pulse() or True))
            def _do_world():
                try:
                    flatten_zip(file_path, tgt, pb6.set_fraction)
                    GLib.idle_add(self._notify, "success", "World Imported", name)
                except Exception as e:
                    GLib.idle_add(self._notify, "error", "Failed", str(e))
                finally:
                    GLib.idle_add(pw.destroy); GLib.idle_add(self._rebuild_storage)
            threading.Thread(target=_do_world, daemon=True).start()
        else:
            ptype = detect_pack_type_from_zip(file_path)
            dest_root = BEHAVIOUR_DIR if ptype == "behavior" else RESOURCE_DIR
            tgt = os.path.join(dest_root, name); n2 = 1
            while os.path.exists(tgt): tgt = os.path.join(dest_root, f"{name}_{n2}"); n2 += 1
            os.makedirs(tgt, exist_ok=True)
            pw, pb6 = show_progress_window(self, "Importing Pack", f"Extracting {name}…")
            GLib.timeout_add(120, lambda: pw.get_visible() and (pb6.pulse() or True))
            def _do_pack():
                try:
                    flatten_zip(file_path, tgt, pb6.set_fraction)
                    GLib.idle_add(self._notify, "success", f"Pack Imported ({ptype})", name)
                except Exception as e:
                    GLib.idle_add(self._notify, "error", "Failed", str(e))
                finally:
                    GLib.idle_add(pw.destroy); GLib.idle_add(self._rebuild_storage)
            threading.Thread(target=_do_pack, daemon=True).start()

    def _import_background(self, *_):
        fd=Gtk.FileChooserDialog(title="Import Background",parent=self,action=Gtk.FileChooserAction.OPEN)
        fd.add_buttons(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,Gtk.STOCK_OPEN,Gtk.ResponseType.OK)
        ff=Gtk.FileFilter(); ff.set_name("Images")
        for p in ("*.png","*.jpg","*.jpeg"): ff.add_pattern(p)
        fd.add_filter(ff)
        if fd.run()!=Gtk.ResponseType.OK: fd.destroy(); return
        src=fd.get_filename(); fd.destroy()
        try:
            dn=os.path.basename(src); dst=os.path.join(BG_DIR,dn); base,ext=os.path.splitext(dst)
            i=1
            while os.path.exists(dst): dst=f"{base}-{i}{ext}"; i+=1
            shutil.copy2(src,dst); self._notify("success","Background Imported",dn)
            GLib.idle_add(self._rebuild_settings); GLib.idle_add(self._rebuild_home)
        except Exception as e: self._notify("error","Import Failed",str(e))

    def _import_theme(self, *_):
        fd=Gtk.FileChooserDialog(title="Import Theme",parent=self,action=Gtk.FileChooserAction.OPEN)
        fd.add_buttons(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,Gtk.STOCK_OPEN,Gtk.ResponseType.OK)
        ff=Gtk.FileFilter(); ff.set_name("CSS"); ff.add_pattern("*.css"); fd.add_filter(ff)
        if fd.run()!=Gtk.ResponseType.OK: fd.destroy(); return
        src=fd.get_filename(); fd.destroy()
        try:
            dn=os.path.basename(src); dst=os.path.join(THEME_DIR,dn); base,ext=os.path.splitext(dst)
            i=1
            while os.path.exists(dst): dst=f"{base}-{i}{ext}"; i+=1
            shutil.copy2(src,dst); self._notify("success","Theme Imported",dn)
            GLib.idle_add(self._rebuild_settings)
        except Exception as e: self._notify("error","Import Failed",str(e))

    def _delete_world(self, path):
        name=os.path.basename(path)
        if not self._confirm(f"Delete world '{name}'?"): return
        try: shutil.rmtree(path); self._notify("success","Deleted",f"World {name} deleted")
        except Exception as e: self._notify("error","Delete Failed",str(e))
        GLib.idle_add(self._rebuild_storage)

    def _delete_modpack(self, base_dir):
        name=os.path.basename(base_dir)
        if not self._confirm(f"Delete '{name}' and all its files?"): return
        try: shutil.rmtree(base_dir); self._notify("success","Deleted",f"{name} deleted")
        except Exception as e: self._notify("error","Delete Failed",str(e))
        GLib.idle_add(self._rebuild_modpacks)

    def _edit_profile_dialog(self):
        profile=load_profile()
        dlg=Gtk.Dialog(title="Edit Profile",parent=self,flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL,Gtk.ResponseType.CANCEL,Gtk.STOCK_OK,Gtk.ResponseType.OK)
        dlg.set_default_size(460,320)
        ca = dlg.get_content_area()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18); box.set_margin_bottom(18); box.set_margin_start(22); box.set_margin_end(22)
        ca.add(box)
        # Username
        un_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        un_lbl = Gtk.Label(label="Username:", xalign=1); un_lbl.set_size_request(100,-1)
        en = Gtk.Entry(); en.set_text(profile.get("username","Player")); en.set_hexpand(True)
        un_row.pack_start(un_lbl, False, False, 0); un_row.pack_start(en, True, True, 0)
        box.pack_start(un_row, False, False, 0)
        # Bio
        bio_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bio_lbl = Gtk.Label(label="Bio:", xalign=1); bio_lbl.set_size_request(100,-1)
        eb = Gtk.Entry(); eb.set_text(profile.get("bio","")); eb.set_placeholder_text("Short bio…"); eb.set_hexpand(True)
        bio_row.pack_start(bio_lbl, False, False, 0); bio_row.pack_start(eb, True, True, 0)
        box.pack_start(bio_row, False, False, 0)
        # Profile picture
        pic_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        pic_lbl = Gtk.Label(label="Picture:", xalign=1); pic_lbl.set_size_request(100,-1)
        selected_pic = [profile.get("profile_picture")]
        cur_name = os.path.basename(selected_pic[0]) if selected_pic[0] else "No picture set"
        pic_name_lbl = Gtk.Label(label=cur_name, xalign=0); pic_name_lbl.set_hexpand(True)
        pic_name_lbl.get_style_context().add_class("version-id")
        def _pick_pic(*_):
            fd = Gtk.FileChooserDialog(title="Select Profile Picture", parent=dlg, action=Gtk.FileChooserAction.OPEN)
            fd.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
            ff = Gtk.FileFilter(); ff.set_name("Images"); ff.add_pattern("*.png"); ff.add_pattern("*.jpg"); ff.add_pattern("*.jpeg"); fd.add_filter(ff)
            if fd.run() == Gtk.ResponseType.OK:
                path = fd.get_filename()
                selected_pic[0] = path
                pic_name_lbl.set_text(os.path.basename(path))
            fd.destroy()
        def _clear_pic(*_):
            selected_pic[0] = None; pic_name_lbl.set_text("No picture set")
        pick_btn = styled_button("Browse…", "mini-btn"); pick_btn.connect("clicked", _pick_pic)
        clear_btn = styled_button("Clear", "mini-btn"); clear_btn.connect("clicked", _clear_pic)
        pic_row.pack_start(pic_lbl, False, False, 0)
        pic_row.pack_start(pic_name_lbl, True, True, 0)
        pic_row.pack_start(pick_btn, False, False, 0)
        pic_row.pack_start(clear_btn, False, False, 0)
        box.pack_start(pic_row, False, False, 0)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL); sep.set_margin_top(8)
        box.pack_start(sep, False, False, 0)
        reset_btn = styled_button("Reset Statistics","del-btn"); reset_btn.set_halign(Gtk.Align.START)
        def _reset_stats(*_):
            if self._confirm("Reset all statistics? This cannot be undone."):
                save_playtime({})
                p2 = load_profile(); p2["launches"] = 0; save_profile(p2)
                self._notify("info","Stats Reset","All statistics cleared")
        reset_btn.connect("clicked", _reset_stats)
        box.pack_start(reset_btn, False, False, 0)
        dlg.show_all()
        if dlg.run()==Gtk.ResponseType.OK:
            profile["username"]=en.get_text().strip() or "Player"
            profile["bio"]=eb.get_text().strip()
            profile["profile_picture"]=selected_pic[0]
            save_profile(profile)
            self._notify("success","Profile Updated",profile["username"])
            self._rebuild_profile_btn_inner(); GLib.idle_add(self._rebuild_profile)
        dlg.destroy()

    def _build_shortcuts_panel(self):
        """Settings → Shortcuts tab content."""
        shortcuts = load_shortcuts()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(26); box.set_margin_end(26); box.set_margin_bottom(26)

        # Section label
        box.pack_start(self._section_lbl("KEY BINDINGS"), False, False, 0)

        # One row per action
        for action, label, _default in SHORTCUT_ACTIONS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.get_style_context().add_class("settings-row")

            # Action description
            desc_lbl = Gtk.Label(label=label, xalign=0)
            desc_lbl.set_hexpand(True)
            desc_lbl.get_style_context().add_class("version-name")
            row.pack_start(desc_lbl, True, True, 0)

            # Current binding display
            cur = shortcuts.get(action, _default)
            display = Gtk.accelerator_get_label(*Gtk.accelerator_parse(cur)) if cur else "—"
            key_lbl = Gtk.Label(label=display if display else cur)
            key_lbl.get_style_context().add_class("shortcut-key-badge")
            key_lbl.set_size_request(120, -1)
            row.pack_start(key_lbl, False, False, 0)

            # Change button
            change_btn = styled_button("Change", "mini-btn")
            make_clickable(change_btn)

            def _on_change(_btn, act=action, lbl=key_lbl, dflt=_default):
                new_key = self._capture_shortcut_dialog(act)
                if new_key is None: return          # cancelled
                sc = load_shortcuts()
                if new_key == "":                   # cleared
                    sc[act] = dflt
                else:
                    sc[act] = new_key
                save_shortcuts(sc)
                disp = Gtk.accelerator_get_label(*Gtk.accelerator_parse(sc[act])) if sc[act] else "—"
                lbl.set_text(disp if disp else sc[act])
                self._apply_shortcuts()

            change_btn.connect("clicked", _on_change)
            row.pack_start(change_btn, False, False, 0)

            # Reset button
            reset_btn = styled_button("↺", "mini-btn")
            reset_btn.set_tooltip_text("Reset to default")
            make_clickable(reset_btn)

            def _on_reset(_btn, act=action, dflt=_default, lbl=key_lbl):
                sc = load_shortcuts(); sc[act] = dflt; save_shortcuts(sc)
                disp = Gtk.accelerator_get_label(*Gtk.accelerator_parse(dflt)) if dflt else "—"
                lbl.set_text(disp if disp else dflt)
                self._apply_shortcuts()

            reset_btn.connect("clicked", _on_reset)
            row.pack_start(reset_btn, False, False, 0)
            box.pack_start(row, False, False, 0)

        # Reset all button
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL); sep.set_margin_top(10)
        box.pack_start(sep, False, False, 0)
        reset_all = styled_button("Reset All to Defaults", "secondary-btn")
        reset_all.set_halign(Gtk.Align.START); reset_all.set_margin_top(6)
        def _reset_all(*_):
            if not self._confirm("Reset all shortcuts to defaults?"): return
            save_shortcuts(dict(DEFAULT_SHORTCUTS))
            self._apply_shortcuts()
            self._notify("info", "Shortcuts Reset", "All shortcuts restored to defaults")
            GLib.idle_add(self._rebuild_settings)
        reset_all.connect("clicked", _reset_all)
        box.pack_start(reset_all, False, False, 0)
        return box

    def _capture_shortcut_dialog(self, action_name):
        """Opens a dialog that waits for the user to press a key combo.
        Returns the accelerator string, "" to clear, or None if cancelled."""
        dlg = Gtk.Dialog(title="Set Shortcut", parent=self, flags=0)
        dlg.add_buttons("Clear", Gtk.ResponseType.REJECT,
                        Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dlg.set_default_size(360, 200)

        ca = dlg.get_content_area()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24); box.set_margin_bottom(16)
        box.set_margin_start(28); box.set_margin_end(28)
        ca.add(box)

        # Find human label for this action
        human = next((lbl for a, lbl, _ in SHORTCUT_ACTIONS if a == action_name), action_name)
        instr = Gtk.Label(wrap=True, xalign=0.5)
        instr.set_markup(f"Press a key combination for\n<b>{human}</b>")
        instr.get_style_context().add_class("version-name")
        box.pack_start(instr, False, False, 0)

        captured = Gtk.Label(label="Waiting for key press…")
        captured.get_style_context().add_class("shortcut-key-badge")
        captured.set_halign(Gtk.Align.CENTER)
        box.pack_start(captured, False, False, 0)

        result = [None]   # None = cancelled, "" = cleared, str = new key

        def _on_key(widget, event):
            # Ignore bare modifier presses
            if event.keyval in (Gdk.KEY_Control_L, Gdk.KEY_Control_R,
                                Gdk.KEY_Shift_L,   Gdk.KEY_Shift_R,
                                Gdk.KEY_Alt_L,     Gdk.KEY_Alt_R,
                                Gdk.KEY_Super_L,   Gdk.KEY_Super_R): return True
            mods = event.state & Gtk.accelerator_get_default_mod_mask()
            key_str = Gtk.accelerator_name(event.keyval, mods)
            disp    = Gtk.accelerator_get_label(event.keyval, mods)
            result[0] = key_str
            captured.set_text(disp if disp else key_str)
            dlg.response(Gtk.ResponseType.OK)
            return True

        dlg.connect("key-press-event", _on_key)
        dlg.show_all()
        resp = dlg.run()
        dlg.destroy()

        if resp == Gtk.ResponseType.OK:     return result[0]
        if resp == Gtk.ResponseType.REJECT: return ""   # "Clear"
        return None                                     # Cancelled

    def _on_splash_done(self):
        self._splash = None
        self._main_root.show_all()
        self._show_home()

    def _profile_play(self):
        """Ctrl+P: play the currently selected/default version."""
        settings = load_settings()
        def_id = settings.get("default_version")
        versions = []
        for d in sorted(os.listdir(GAME_DIR)):
            ip = os.path.join(GAME_DIR, d, "version_info.json")
            if not os.path.isdir(os.path.join(GAME_DIR, d)) or not os.path.exists(ip): continue
            try:
                info = json.load(open(ip))
                if info.get("beta") and not settings.get("allow_beta"): continue
                versions.append(info.get("version_id", d))
            except Exception: continue
        if not versions: self._notify("error", "No Versions", "Install a version first"); return
        vid = def_id if def_id in versions else versions[-1]
        self._launch_version(vid)

    def _show_shortcuts_help(self):
        """Ctrl+/: show a shortcuts reference dialog."""
        dlg = Gtk.Dialog(title="Keyboard Shortcuts", parent=self, flags=0)
        dlg.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        dlg.set_default_size(400, 360)
        ca = dlg.get_content_area()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_margin_top(16); box.set_margin_bottom(16)
        box.set_margin_start(24); box.set_margin_end(24)
        ca.add(box)
        title = Gtk.Label(xalign=0)
        title.set_markup("<b>Keyboard Shortcuts</b>")
        title.get_style_context().add_class("page-title")
        title.set_margin_bottom(14)
        box.pack_start(title, False, False, 0)
        shortcuts = [
            ("Ctrl + H",     "Home"),
            ("Ctrl + V",     "Versions"),
            ("Ctrl + E",     "Servers"),
            ("Ctrl + S",     "Storage"),
            ("Ctrl + I",     "Import"),
            ("Ctrl + ,",     "Settings"),
            ("Ctrl + P",     "Play default version"),
            ("Ctrl + R",     "Reload launcher"),
            ("Ctrl + /",     "Show this help"),
        ]
        for key, desc in shortcuts:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.get_style_context().add_class("settings-row")
            row.set_margin_bottom(4)
            key_lbl = Gtk.Label(label=key, xalign=0)
            key_lbl.set_size_request(120, -1)
            key_lbl.get_style_context().add_class("version-name")
            desc_lbl = Gtk.Label(label=desc, xalign=0)
            desc_lbl.get_style_context().add_class("version-id")
            row.pack_start(key_lbl, False, False, 0)
            row.pack_start(desc_lbl, True, True, 0)
            box.pack_start(row, False, False, 0)
        dlg.show_all()
        dlg.run(); dlg.destroy()

    def _restart(self):
        args = [a for a in sys.argv if a != "--no-splash"] + ["--no-splash"]
        try: sys.stdout.flush(); sys.stderr.flush(); os.execv(sys.executable, [sys.executable] + args)
        except Exception as e: print(f"[restart] {e}", flush=True)


if __name__ == "__main__":
    win = Launcher()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()