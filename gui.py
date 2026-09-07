#!/usr/bin/env python3
"""Interface graphique PySide6 pour le clavier EPOMAKER / AULA EA75 (MAX).

    python3 gui.py

Note : tout le texte visible est en anglais (demande utilisateur) ; les
commentaires et la doc restent en francais.

Onglets : Lighting (effet global) / Per-key / Remap / Calibration / Profiles.
Le clavier ne renvoie jamais son etat : la GUI est la source de verite et
repousse la configuration au clavier ("Apply").
"""

from __future__ import annotations

import dataclasses
import json
import sys
import threading
import traceback
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import epomaker
import layout_ea75

CONFIG_DIR = Path.home() / ".config" / "epomaker-gui"
PROFILE_DIR = CONFIG_DIR / "profiles"
OVERRIDES_FILE = CONFIG_DIR / "layout_overrides.json"
LAST_FILE = CONFIG_DIR / "last.json"

UNIT = 46          # pixels par "U" de clavier
KEY_GAP = 5
ROW_H = 47

# --- palette --------------------------------------------------------------
BG = "#15151b"
PANEL = "#1e1e27"
PANEL_HI = "#262631"
STROKE = "#32323f"
ACCENT = "#5a7dff"
TEXT = "#e6e6ec"
MUTED = "#8b8b9a"
KEY_BG = "#2b2b36"

STYLE = f"""
* {{ font-family: "Inter", "SF Pro Text", "Segoe UI", "Cantarell", sans-serif; }}
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {STROKE}; border-radius: 14px; }}
QLabel#h1 {{ font-size: 16px; font-weight: 600; }}
QLabel#section {{ font-size: 10px; font-weight: 700; color: {MUTED}; letter-spacing: 1.5px; }}
QLabel#hint {{ color: {MUTED}; font-size: 12px; }}
QLabel#value {{ color: {ACCENT}; font-weight: 700; min-width: 18px; }}
QLabel#effectdesc {{ color: {MUTED}; font-size: 12px; }}

QPushButton {{
    background: {PANEL_HI}; border: 1px solid {STROKE}; border-radius: 9px;
    padding: 9px 16px; color: {TEXT};
}}
QPushButton:hover {{ background: #30303d; }}
QPushButton:pressed {{ background: #2a2a35; }}
QPushButton#primary {{ background: {ACCENT}; border: none; font-weight: 600; color: white; }}
QPushButton#primary:hover {{ background: #6d8bff; }}
QPushButton#danger {{ background: #3a2531; border-color: #5c3546; color: #ffb3c8; }}
QPushButton#danger:hover {{ background: #472c3b; }}
QPushButton#swatch {{ border-radius: 9px; min-height: 34px; border: 1px solid {STROKE}; }}

QComboBox, QSpinBox {{
    background: #23232d; border: 1px solid {STROKE}; border-radius: 8px;
    padding: 7px 11px; min-height: 18px;
}}
QComboBox:hover, QSpinBox:hover {{ border-color: #45455a; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: #23232d; border: 1px solid {STROKE};
    selection-background-color: {ACCENT}; outline: none;
}}

QSlider {{ min-height: 26px; }}
QSlider::groove:horizontal {{ height: 5px; background: {STROKE}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    background: white; border: 3px solid {ACCENT};
}}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 6px;
    border: 1px solid {STROKE}; background: #23232d;
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QTabWidget::pane {{ border: none; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; padding: 10px 16px; margin-right: 4px;
    color: {MUTED}; border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QListWidget {{ background: #23232d; border: 1px solid {STROKE}; border-radius: 10px; padding: 4px; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {ACCENT}; color: white; }}

QStatusBar {{ background: #101017; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QDialog {{ background: {PANEL}; }}
QScrollArea {{ border: none; background: transparent; }}
QToolTip {{ background: {PANEL_HI}; color: {TEXT}; border: 1px solid {STROKE}; }}
"""

EFFECT_DESC = {
    "off": "All LEDs off.",
    "static": "Single solid color.",
    "singleon": "Key lights up when pressed.",
    "singleoff": "Key turns off when pressed.",
    "glittering": "Random sparkles.",
    "falling": "Drops falling down the board.",
    "colourful": "Full-board rainbow cycle.",
    "breath": "Color fades in and out.",
    "spectrum": "Slow rainbow hue shift.",
    "outward": "Waves radiating from the center.",
    "scrolling": "Rainbow scrolling sideways.",
    "rolling": "Rainbow rolling vertically.",
    "rotating": "Colors sweeping in a circle.",
    "explode": "Bursts from each keypress.",
    "launch": "Trails shooting upward.",
    "ripples": "Ripples spreading from keypress.",
    "flowing": "Smooth flowing gradient.",
    "pulsating": "Whole board pulsing.",
    "tilt": "Diagonal color sweep.",
    "shuttle": "Back-and-forth light beam.",
}


# ---------------------------------------------------------------------------
# Profil
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Profile:
    name: str = "unnamed"
    effect: str = "static"
    color: list = dataclasses.field(default_factory=lambda: [255, 255, 255])
    brightness: int = 5
    speed: int = 3
    direction: int = 0
    rainbow: bool = False
    per_key: dict = dataclasses.field(default_factory=dict)
    per_key_brightness: int = 5
    per_key_enabled: bool = False
    remap: dict = dataclasses.field(default_factory=lambda: {"normal": {}, "fn": {}})

    def to_json(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Profile":
        f = {k.name for k in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in f})


def load_overrides() -> dict:
    try:
        return {k: int(v) for k, v in json.loads(OVERRIDES_FILE.read_text()).items()}
    except (OSError, ValueError):
        return {}


def save_overrides(ov: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(ov, indent=2))


def index_map() -> dict:
    m = layout_ea75.default_index_map()
    m.update(load_overrides())
    return m


# ---------------------------------------------------------------------------
# Appels device en arriere-plan
# ---------------------------------------------------------------------------

class Worker(QtCore.QObject):
    done = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def run(self, label: str, fn):
        def target():
            try:
                with epomaker.Keyboard() as kb:
                    fn(kb)
                self.done.emit(label)
            except Exception as exc:                      # noqa: BLE001
                self.failed.emit(f"{label}: {exc}")
                traceback.print_exc()

        threading.Thread(target=target, daemon=True).start()


# ---------------------------------------------------------------------------
# Petits helpers UI
# ---------------------------------------------------------------------------

def card(*children, spacing=12, margins=(16, 16, 16, 16)) -> QtWidgets.QFrame:
    f = QtWidgets.QFrame()
    f.setObjectName("card")
    lay = QtWidgets.QVBoxLayout(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for c in children:
        if isinstance(c, QtWidgets.QLayout):
            lay.addLayout(c)
        else:
            lay.addWidget(c)
    return f


def section_label(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text.upper())
    lbl.setObjectName("section")
    return lbl


def hint_label(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("hint")
    lbl.setWordWrap(True)
    return lbl


def rainbow_color(col_ratio: float) -> QtGui.QColor:
    c = QtGui.QColor()
    c.setHsvF(col_ratio % 1.0, 0.85, 1.0)
    return c


def dim(c: QtGui.QColor, brightness: int) -> QtGui.QColor:
    k = 0.30 + 0.70 * (brightness / 5)
    return QtGui.QColor(int(c.red() * k), int(c.green() * k), int(c.blue() * k))


# ---------------------------------------------------------------------------
# Widget clavier
# ---------------------------------------------------------------------------

class KeyboardWidget(QtWidgets.QWidget):
    keyClicked = QtCore.Signal(str)
    keyRightClicked = QtCore.Signal(str)

    def __init__(self, interactive: bool = True):
        super().__init__()
        self.interactive = interactive
        self._rects: list[tuple[QtCore.QRectF, tuple]] = []
        self.colors: dict[str, QtGui.QColor] = {}
        self.badges: dict[str, str] = {}
        self.highlight: set[str] = set()
        self._hover: str | None = None
        self._maxx = 0
        self.setMouseTracking(interactive)
        self._build()

    def _build(self):
        self._rects.clear()
        maxx = 0.0
        for r, x, key in layout_ea75.iter_keys():
            label, kid, w, hid, index = key
            rx = 12 + x * UNIT
            ry = 12 + r * (ROW_H + KEY_GAP)
            rw = w * UNIT - KEY_GAP
            rect = QtCore.QRectF(rx, ry, rw, ROW_H - KEY_GAP)
            self._rects.append((rect, key))
            maxx = max(maxx, rx + rw)
        self._maxx = maxx
        h = 12 + 6 * (ROW_H + KEY_GAP) + 12
        self.setMinimumSize(int(maxx + 24), int(h))

    def sizeHint(self):
        return QtCore.QSize(int(self._maxx + 24), 12 + 6 * (ROW_H + KEY_GAP) + 12)

    # -- interaction ----------------------------------------------------------

    def _hit(self, pos):
        for rect, key in self._rects:
            if rect.contains(pos):
                return key[1]
        return None

    def mouseMoveEvent(self, e):
        if not self.interactive:
            return
        kid = self._hit(e.position())
        if kid != self._hover:
            self._hover = kid
            self.setCursor(QtCore.Qt.PointingHandCursor if kid
                           else QtCore.Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        if not self.interactive:
            return
        kid = self._hit(e.position())
        if not kid:
            return
        if e.button() == QtCore.Qt.LeftButton:
            self.keyClicked.emit(kid)
        elif e.button() == QtCore.Qt.RightButton:
            self.keyRightClicked.emit(kid)

    # -- rendu --------------------------------------------------------------

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        f = p.font()
        f.setPointSize(8)
        p.setFont(f)

        for rect, key in self._rects:
            label, kid, w, hid, index = key
            bg = self.colors.get(kid) or QtGui.QColor(KEY_BG)
            p.setBrush(bg)

            if kid in self.highlight:
                p.setPen(QtGui.QPen(QtGui.QColor("#ffd24d"), 2))
            elif kid == self._hover:
                p.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 2))
            else:
                p.setPen(QtGui.QPen(QtGui.QColor("#101014")))

            if kid == "knob":
                p.drawEllipse(rect)
            else:
                p.drawRoundedRect(rect, 6, 6)

            lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
            p.setPen(QtGui.QColor("#111") if lum > 150 else QtGui.QColor("#cfcfd6"))
            p.drawText(rect, QtCore.Qt.AlignCenter, label)

            badge = self.badges.get(kid)
            if badge:
                p.setPen(QtGui.QColor("#ffd24d"))
                br = QtCore.QRectF(rect.left() - 4, rect.top() - 11,
                                   rect.width() + 8, 11)
                bf = p.font()
                bf.setPointSize(7)
                p.setFont(bf)
                p.drawText(br, QtCore.Qt.AlignCenter, badge)
                p.setFont(f)


# ---------------------------------------------------------------------------
# Slider avec badge de valeur
# ---------------------------------------------------------------------------

class LabeledSlider(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(int)

    def __init__(self, lo, hi, val):
        super().__init__()
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(val)
        self.badge = QtWidgets.QLabel(str(val))
        self.badge.setObjectName("value")
        self.badge.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.slider.valueChanged.connect(lambda v: self.badge.setText(str(v)))
        self.slider.valueChanged.connect(self.valueChanged)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.badge)

    def value(self):
        return self.slider.value()

    def setValue(self, v):
        self.slider.setValue(v)


# ---------------------------------------------------------------------------
# Onglet : Lighting (effet global)
# ---------------------------------------------------------------------------

class EffectsTab(QtWidgets.QWidget):
    def __init__(self, app: "MainWindow"):
        super().__init__()
        self.app = app
        self._color = QtGui.QColor(255, 255, 255)

        # -- controles -----------------------------------------------------
        self.effect = QtWidgets.QComboBox()
        for name in sorted(epomaker.MODES):
            self.effect.addItem(name.capitalize(), name)
        self.effect.currentIndexChanged.connect(self._on_change)

        self.desc = QtWidgets.QLabel()
        self.desc.setObjectName("effectdesc")
        self.desc.setWordWrap(True)

        self.swatch = QtWidgets.QPushButton()
        self.swatch.setObjectName("swatch")
        self.swatch.clicked.connect(self._pick_color)

        self.rainbow = QtWidgets.QCheckBox("Rainbow (per-key hue, ignores color)")
        self.rainbow.toggled.connect(self._on_change)

        self.brightness = LabeledSlider(0, 5, 5)
        self.speed = LabeledSlider(0, 5, 3)
        self.brightness.valueChanged.connect(self._on_change)
        self.speed.valueChanged.connect(self._on_change)

        self.reverse = QtWidgets.QCheckBox("Reverse direction")
        self.reverse.toggled.connect(self._on_change)

        grid = QtWidgets.QGridLayout()
        grid.setVerticalSpacing(14)
        grid.setHorizontalSpacing(14)
        grid.addWidget(QtWidgets.QLabel("Color"), 0, 0)
        grid.addWidget(self.swatch, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Brightness"), 1, 0)
        grid.addWidget(self.brightness, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Speed"), 2, 0)
        grid.addWidget(self.speed, 2, 1)
        grid.setColumnStretch(1, 1)

        self.apply_btn = QtWidgets.QPushButton("Apply")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self.apply)
        off_btn = QtWidgets.QPushButton("Turn off")
        off_btn.setObjectName("danger")
        off_btn.clicked.connect(lambda: self.app.device("Lights off", lambda kb: kb.off()))
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(self.apply_btn, 1)
        btn_row.addWidget(off_btn)

        controls = card(
            section_label("Effect"),
            self.effect,
            self.desc,
            _spacer(4),
            section_label("Parameters"),
            grid,
            self.rainbow,
            self.reverse,
            _spacer(4),
            btn_row,
        )
        controls.setFixedWidth(340)

        # -- preview -----------------------------------------------------
        self.preview = KeyboardWidget(interactive=False)
        prev_card = card(
            section_label("Preview"),
            self.preview,
            hint_label("Approximate — the real effect (animation, direction) "
                       "plays on the keyboard after you press Apply."),
        )

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)
        row.addWidget(controls)
        row.addWidget(prev_card, 1)

        self._refresh_swatch()
        self._on_change()

    def _refresh_swatch(self):
        c = self._color
        self.swatch.setText(f"#{c.red():02x}{c.green():02x}{c.blue():02x}".upper())
        fg = "#000" if c.lightness() > 130 else "#fff"
        self.swatch.setStyleSheet(
            f"#swatch {{ background: {c.name()}; color: {fg}; }}")

    def _pick_color(self):
        c = QtWidgets.QColorDialog.getColor(self._color, self, "Effect color")
        if c.isValid():
            self._color = c
            self._refresh_swatch()
            self._on_change()

    def _on_change(self, *_):
        name = self.effect.currentData()
        self.desc.setText(EFFECT_DESC.get(name, ""))
        is_off = name == "off"
        colorful = name in ("colourful", "spectrum")
        self.swatch.setEnabled(not is_off and not self.rainbow.isChecked() and not colorful)
        self.rainbow.setEnabled(not is_off and not colorful)
        self.brightness.setEnabled(not is_off)
        self.speed.setEnabled(not is_off)
        self._update_preview()

    def _update_preview(self):
        name = self.effect.currentData()
        b = self.brightness.value()
        if name == "off":
            self.preview.colors = {k[1]: QtGui.QColor("#0c0c10")
                                   for _, _, k in layout_ea75.iter_keys()}
        elif self.rainbow.isChecked() or name in ("colourful", "spectrum",
                                                  "scrolling", "rolling"):
            cols = {}
            for _, x, k in layout_ea75.iter_keys():
                cols[k[1]] = dim(rainbow_color(x / 15.0), b)
            self.preview.colors = cols
        else:
            c = dim(self._color, b)
            self.preview.colors = {k[1]: c for _, _, k in layout_ea75.iter_keys()}
        self.preview.update()

    # -- profil <-> UI --------------------------------------------------

    def load(self, p: Profile):
        i = self.effect.findData(p.effect)
        self.effect.setCurrentIndex(max(0, i))
        self._color = QtGui.QColor(*p.color)
        self.rainbow.setChecked(p.rainbow)
        self.brightness.setValue(p.brightness)
        self.speed.setValue(p.speed)
        self.reverse.setChecked(bool(p.direction))
        self._refresh_swatch()
        self._on_change()

    def save(self, p: Profile):
        p.effect = self.effect.currentData()
        p.color = [self._color.red(), self._color.green(), self._color.blue()]
        p.rainbow = self.rainbow.isChecked()
        p.brightness = self.brightness.value()
        p.speed = self.speed.value()
        p.direction = int(self.reverse.isChecked())

    def apply(self):
        self.save(self.app.profile)
        p = self.app.profile
        mode = epomaker.MODES[p.effect]
        r, g, b = p.color
        self.app.device(
            f"Effect '{p.effect}'",
            lambda kb: kb.set_lighting(mode, r, g, b, brightness=p.brightness,
                                       speed=p.speed, direction=p.direction,
                                       rainbow=p.rainbow))


def _spacer(h: int) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    w.setFixedHeight(h)
    return w


# ---------------------------------------------------------------------------
# Onglet : Per-key
# ---------------------------------------------------------------------------

class PerKeyTab(QtWidgets.QWidget):
    def __init__(self, app: "MainWindow"):
        super().__init__()
        self.app = app
        self._color = QtGui.QColor(255, 40, 40)

        self.kb = KeyboardWidget()
        self.kb.keyClicked.connect(self._paint)
        self.kb.keyRightClicked.connect(self._clear_key)

        self.swatch = QtWidgets.QPushButton()
        self.swatch.setObjectName("swatch")
        self.swatch.clicked.connect(self._pick)
        self._refresh_btn()

        fill = QtWidgets.QPushButton("Paint all")
        fill.clicked.connect(self._fill_all)
        clear = QtWidgets.QPushButton("Clear all")
        clear.clicked.connect(self._clear_all)

        self.bright = LabeledSlider(0, 5, 5)

        apply_btn = QtWidgets.QPushButton("Apply to keyboard")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self.apply)

        tools = card(
            section_label("Brush"),
            self.swatch,
            fill, clear,
            _spacer(4),
            section_label("Brightness"),
            self.bright,
            _spacer(4),
            apply_btn,
            hint_label("Left-click paints a key, right-click clears it. "
                       "Unpainted keys stay off. Calibrate the light indices "
                       "first if colors land on the wrong keys."),
        )
        tools.setFixedWidth(300)
        tools.layout().addStretch()

        board = card(section_label("Keyboard"), self._scroll(self.kb))

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)
        row.addWidget(tools)
        row.addWidget(board, 1)

    def _scroll(self, w):
        sa = QtWidgets.QScrollArea()
        sa.setWidget(w)
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        return sa

    def _refresh_btn(self):
        self.swatch.setStyleSheet(f"#swatch {{ background: {self._color.name()}; }}")
        self.swatch.setText(self._color.name().upper())

    def _pick(self):
        c = QtWidgets.QColorDialog.getColor(self._color, self, "Brush color")
        if c.isValid():
            self._color = c
            self._refresh_btn()

    def _paint(self, kid):
        self.app.profile.per_key[kid] = [
            self._color.red(), self._color.green(), self._color.blue()]
        self._sync()

    def _clear_key(self, kid):
        self.app.profile.per_key.pop(kid, None)
        self._sync()

    def _fill_all(self):
        rgb = [self._color.red(), self._color.green(), self._color.blue()]
        for _, _, k in layout_ea75.iter_keys():
            if k[4] is not None:
                self.app.profile.per_key[k[1]] = list(rgb)
        self._sync()

    def _clear_all(self):
        self.app.profile.per_key.clear()
        self._sync()

    def _sync(self):
        self.kb.colors = {kid: QtGui.QColor(*rgb)
                          for kid, rgb in self.app.profile.per_key.items()}
        self.kb.update()

    def load(self, p: Profile):
        self.bright.setValue(p.per_key_brightness)
        self._sync()

    def save(self, p: Profile):
        p.per_key_brightness = self.bright.value()
        p.per_key_enabled = bool(p.per_key)

    def apply(self):
        self.save(self.app.profile)
        imap = index_map()
        colors = {imap[k]: tuple(v) for k, v in self.app.profile.per_key.items()
                  if k in imap}
        if not colors:
            self.app.status("Nothing to apply — no keys painted.")
            return
        b = self.bright.value()
        self.app.device(f"{len(colors)} key(s)",
                        lambda kb: kb.set_per_key_rgb(colors, brightness=b))


# ---------------------------------------------------------------------------
# Onglet : Remap
# ---------------------------------------------------------------------------

REMAP_TARGETS_KEY = list(epomaker.HID_CODE)
REMAP_TARGETS_CONSUMER = list(epomaker.CONSUMER_CODE)
REMAP_TARGETS_MOUSE = list(epomaker.MOUSE_PARAMS)


class RemapDialog(QtWidgets.QDialog):
    def __init__(self, parent, key_label, current):
        super().__init__(parent)
        self.setWindowTitle(f"Remap: {key_label}")
        self.setMinimumWidth(380)
        self.spec = None

        self.kind = QtWidgets.QComboBox()
        self.kind.addItems(["No remap (default)", "Key", "Combo (Ctrl/Alt/Shift/Win + key)",
                            "Media", "Mouse"])
        self.stack = QtWidgets.QStackedWidget()

        self.stack.addWidget(hint_label("The key keeps its original behavior."))

        self.key_combo = QtWidgets.QComboBox()
        self.key_combo.addItems(REMAP_TARGETS_KEY)
        self.stack.addWidget(self._wrap("Send key:", self.key_combo))

        w = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(w)
        g.setContentsMargins(0, 0, 0, 0)
        self.m_ctrl = QtWidgets.QCheckBox("Ctrl")
        self.m_shift = QtWidgets.QCheckBox("Shift")
        self.m_alt = QtWidgets.QCheckBox("Alt")
        self.m_win = QtWidgets.QCheckBox("Win")
        self.combo_key = QtWidgets.QComboBox()
        self.combo_key.addItems(REMAP_TARGETS_KEY)
        g.addWidget(self.m_ctrl, 0, 0)
        g.addWidget(self.m_shift, 0, 1)
        g.addWidget(self.m_alt, 0, 2)
        g.addWidget(self.m_win, 0, 3)
        g.addWidget(QtWidgets.QLabel("+ key"), 1, 0)
        g.addWidget(self.combo_key, 1, 1, 1, 3)
        self.stack.addWidget(w)

        self.cons = QtWidgets.QComboBox()
        self.cons.addItems(REMAP_TARGETS_CONSUMER)
        self.stack.addWidget(self._wrap("Media action:", self.cons))

        self.mouse = QtWidgets.QComboBox()
        self.mouse.addItems(REMAP_TARGETS_MOUSE)
        self.stack.addWidget(self._wrap("Mouse action:", self.mouse))

        self.kind.currentIndexChanged.connect(self.stack.setCurrentIndex)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(self.kind)
        lay.addWidget(self.stack)
        lay.addWidget(bb)
        self._load_current(current)

    def _wrap(self, text, widget):
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QtWidgets.QLabel(text))
        h.addWidget(widget, 1)
        return w

    def _load_current(self, cur):
        if not cur:
            return
        t = cur.get("type")
        if t == "key":
            self.kind.setCurrentIndex(1)
            self.key_combo.setCurrentText(cur["key"])
        elif t == "combo":
            self.kind.setCurrentIndex(2)
            self.m_ctrl.setChecked(cur.get("ctrl", False))
            self.m_shift.setChecked(cur.get("shift", False))
            self.m_alt.setChecked(cur.get("alt", False))
            self.m_win.setChecked(cur.get("win", False))
            self.combo_key.setCurrentText(cur["key"])
        elif t == "consumer":
            self.kind.setCurrentIndex(3)
            self.cons.setCurrentText(cur["key"])
        elif t == "mouse":
            self.kind.setCurrentIndex(4)
            self.mouse.setCurrentText(cur["key"])

    def _accept(self):
        i = self.kind.currentIndex()
        if i == 0:
            self.spec = None
        elif i == 1:
            self.spec = {"type": "key", "key": self.key_combo.currentText()}
        elif i == 2:
            self.spec = {"type": "combo", "key": self.combo_key.currentText(),
                         "ctrl": self.m_ctrl.isChecked(), "shift": self.m_shift.isChecked(),
                         "alt": self.m_alt.isChecked(), "win": self.m_win.isChecked()}
        elif i == 3:
            self.spec = {"type": "consumer", "key": self.cons.currentText()}
        else:
            self.spec = {"type": "mouse", "key": self.mouse.currentText()}
        self.accept()


spec_to_slot = epomaker.spec_to_slot


def spec_badge(spec: dict) -> str:
    t = spec["type"]
    if t == "key":
        return "→" + spec["key"]
    if t == "combo":
        m = "".join(c for c, on in (("C", spec.get("ctrl")), ("S", spec.get("shift")),
                                    ("A", spec.get("alt")), ("W", spec.get("win"))) if on)
        return f"{m}+{spec['key']}"
    if t == "consumer":
        return "media:" + spec["key"]
    if t == "mouse":
        return "mouse:" + spec["key"]
    return "?"


class RemapTab(QtWidgets.QWidget):
    def __init__(self, app: "MainWindow"):
        super().__init__()
        self.app = app
        self.layer = "normal"

        self.kb = KeyboardWidget()
        self.kb.keyClicked.connect(self._edit)
        self.kb.keyRightClicked.connect(self._reset_key)

        self.layer_sel = QtWidgets.QComboBox()
        self.layer_sel.addItems(["Normal layer", "Fn layer"])
        self.layer_sel.currentIndexChanged.connect(self._switch_layer)

        reset = QtWidgets.QPushButton("Reset layer")
        reset.clicked.connect(self._reset_layer)
        apply_btn = QtWidgets.QPushButton("Apply to keyboard")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self.apply)

        tools = card(
            section_label("Layer"),
            self.layer_sel,
            reset,
            _spacer(4),
            apply_btn,
            hint_label("Click a key to assign a remap, right-click to reset it. "
                       "The Fn layer applies while Fn is held. Calibrate light "
                       "indices first."),
        )
        tools.setFixedWidth(300)
        tools.layout().addStretch()

        board = card(section_label("Keyboard"), self._scroll(self.kb))

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)
        row.addWidget(tools)
        row.addWidget(board, 1)

    def _scroll(self, w):
        sa = QtWidgets.QScrollArea()
        sa.setWidget(w)
        sa.setWidgetResizable(True)
        return sa

    def _switch_layer(self, i):
        self.layer = "fn" if i else "normal"
        self._sync()

    def _edit(self, kid):
        key = layout_ea75.key_by_id()[kid]
        cur = self.app.profile.remap[self.layer].get(kid)
        dlg = RemapDialog(self, key[0], cur)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            if dlg.spec is None:
                self.app.profile.remap[self.layer].pop(kid, None)
            else:
                self.app.profile.remap[self.layer][kid] = dlg.spec
            self._sync()

    def _reset_key(self, kid):
        self.app.profile.remap[self.layer].pop(kid, None)
        self._sync()

    def _reset_layer(self):
        self.app.profile.remap[self.layer] = {}
        self._sync()

    def _sync(self):
        self.kb.badges = {kid: spec_badge(s)
                          for kid, s in self.app.profile.remap[self.layer].items()}
        self.kb.highlight = set(self.kb.badges)
        self.kb.update()

    def load(self, p: Profile):
        p.remap.setdefault("normal", {})
        p.remap.setdefault("fn", {})
        self._sync()

    def save(self, p: Profile):
        pass

    def apply(self):
        imap = index_map()
        specs = self.app.profile.remap[self.layer]
        slots = {imap[k]: spec_to_slot(s) for k, s in specs.items() if k in imap}
        fn = self.layer == "fn"
        self.app.device(f"Remap {self.layer} ({len(slots)})",
                        lambda kb: kb.set_key_remap(slots, fn_layer=fn))


# ---------------------------------------------------------------------------
# Onglet : Calibration
# ---------------------------------------------------------------------------

class CalibrationTab(QtWidgets.QWidget):
    def __init__(self, app: "MainWindow"):
        super().__init__()
        self.app = app
        self.overrides = load_overrides()

        self.kb = KeyboardWidget()
        self.kb.keyClicked.connect(self._assign)

        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(1, 140)
        self.spin.setValue(1)
        self.spin.valueChanged.connect(self._sync)

        light = QtWidgets.QPushButton("Light this index")
        light.setObjectName("primary")
        light.clicked.connect(self._light)
        nxt = QtWidgets.QPushButton("Next ›")
        nxt.clicked.connect(lambda: self.spin.setValue(self.spin.value() + 1))
        prv = QtWidgets.QPushButton("‹ Prev")
        prv.clicked.connect(lambda: self.spin.setValue(self.spin.value() - 1))

        save = QtWidgets.QPushButton("Save corrections")
        save.clicked.connect(self._save)
        reset = QtWidgets.QPushButton("Clear corrections")
        reset.setObjectName("danger")
        reset.clicked.connect(self._reset)

        nav = QtWidgets.QHBoxLayout()
        nav.addWidget(prv)
        nav.addWidget(nxt)

        self.info = QtWidgets.QLabel()
        self.info.setObjectName("hint")

        tools = card(
            section_label("Light index"),
            self.spin,
            light,
            nav,
            self.info,
            _spacer(6),
            save, reset,
            hint_label("1. \"Light this index\" turns on a single LED.\n"
                       "2. Click the key that actually lit up — it gets bound "
                       "to this index.\n3. \"Next\" and repeat. Defaults come "
                       "from the F108 Pro; green keys are your corrections."),
        )
        tools.setFixedWidth(320)
        tools.layout().addStretch()

        board = card(section_label("Keyboard"), self._scroll(self.kb))

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)
        row.addWidget(tools)
        row.addWidget(board, 1)
        self._sync()

    def _scroll(self, w):
        sa = QtWidgets.QScrollArea()
        sa.setWidget(w)
        sa.setWidgetResizable(True)
        return sa

    def _light(self):
        idx = self.spin.value()
        self.app.device(f"LED index {idx}",
                        lambda kb: kb.set_per_key_rgb({idx: (0, 255, 0)}, brightness=5))

    def _assign(self, kid):
        idx = self.spin.value()
        for k, v in list(self.overrides.items()):
            if v == idx:
                del self.overrides[k]
        self.overrides[kid] = idx
        self._sync()

    def _save(self):
        save_overrides(self.overrides)
        self.app.status("Corrections saved.")

    def _reset(self):
        self.overrides = {}
        save_overrides({})
        self._sync()

    def _sync(self, *_):
        eff = layout_ea75.default_index_map()
        eff.update(self.overrides)
        rev = {}
        for kid, idx in eff.items():
            rev.setdefault(idx, []).append(kid)
        cur = self.spin.value()
        self.kb.colors = {kid: QtGui.QColor("#2f6f3f") for kid in self.overrides}
        self.kb.highlight = set(rev.get(cur, []))
        self.kb.update()
        match = rev.get(cur, [])
        self.info.setText(f"Index {cur} → " + (", ".join(match) or "(unassigned)")
                          + f"    ·    {len(self.overrides)} correction(s)")


# ---------------------------------------------------------------------------
# Onglet : Screen (horloge de l'ecran LCD)
# ---------------------------------------------------------------------------

class ScreenTab(QtWidgets.QWidget):
    def __init__(self, app: "MainWindow"):
        super().__init__()
        self.app = app

        self.clock_lbl = QtWidgets.QLabel()
        self.clock_lbl.setStyleSheet("font-size: 30px; font-weight: 600;")
        self.clock_lbl.setAlignment(QtCore.Qt.AlignCenter)

        self._tick = QtCore.QTimer(self)
        self._tick.timeout.connect(self._show_time)
        self._tick.start(1000)
        self._show_time()

        sync_btn = QtWidgets.QPushButton("Sync clock now")
        sync_btn.setObjectName("primary")
        sync_btn.clicked.connect(self._sync)

        self.auto = QtWidgets.QCheckBox("Keep the screen clock in sync (every 10 min)")
        self.auto.toggled.connect(self._toggle_auto)
        self._auto_timer = QtCore.QTimer(self)
        self._auto_timer.setInterval(10 * 60 * 1000)
        self._auto_timer.timeout.connect(self._sync)

        c = card(
            section_label("Screen clock"),
            self.clock_lbl,
            sync_btn,
            self.auto,
            hint_label("Pushes the current system date/time to the keyboard's "
                       "LCD clock. The keyboard has no battery-backed clock, so "
                       "re-sync after unplugging it. Only affects models with a "
                       "screen."),
        )
        c.setMaximumWidth(460)
        c.layout().addStretch()

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(c, alignment=QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        lay.addStretch()

    def _show_time(self):
        self.clock_lbl.setText(QtCore.QDateTime.currentDateTime()
                               .toString("ddd  dd MMM  ·  HH:mm:ss"))

    def _toggle_auto(self, on):
        if on:
            self._auto_timer.start()
            self._sync()
        else:
            self._auto_timer.stop()

    def _sync(self):
        self.app.device("Screen clock", lambda kb: kb.sync_clock())

    # -- interface profil (no-op, l'horloge n'est pas dans le profil) --
    def load(self, p):
        pass

    def save(self, p):
        pass


# ---------------------------------------------------------------------------
# Onglet : Profiles
# ---------------------------------------------------------------------------

class ProfilesTab(QtWidgets.QWidget):
    def __init__(self, app: "MainWindow"):
        super().__init__()
        self.app = app

        self.list = QtWidgets.QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._load())

        newb = QtWidgets.QPushButton("New")
        newb.clicked.connect(self._new)
        saveb = QtWidgets.QPushButton("Save")
        saveb.setObjectName("primary")
        saveb.clicked.connect(self._save)
        loadb = QtWidgets.QPushButton("Load")
        loadb.clicked.connect(self._load)
        delb = QtWidgets.QPushButton("Delete")
        delb.setObjectName("danger")
        delb.clicked.connect(self._delete)
        applyb = QtWidgets.QPushButton("Load + apply everything")
        applyb.clicked.connect(self._apply_all)

        btns = card(
            section_label("Profiles"),
            newb, saveb, loadb, delb,
            _spacer(6),
            applyb,
        )
        btns.setFixedWidth(280)

        self.autostart = QtWidgets.QLabel()
        self.autostart.setObjectName("hint")
        self._refresh_autostart()
        auto_btn = QtWidgets.QPushButton("Install \"apply on login\" service")
        auto_btn.clicked.connect(self._install_service)

        auto_card = card(
            section_label("Autostart"),
            self.autostart,
            auto_btn,
            hint_label("Writes a systemd user service that re-applies the "
                       "selected profile after login / re-plug. Enable it with:\n"
                       "systemctl --user enable --now epomaker-gui.service"),
        )
        auto_card.layout().addStretch()

        right = QtWidgets.QVBoxLayout()
        right.addWidget(btns)
        right.addWidget(auto_card, 1)

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(16)
        lay.addWidget(card(section_label("Saved"), self.list), 2)
        lay.addLayout(right, 1)
        self.refresh()

    def refresh(self):
        self.list.clear()
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        for f in sorted(PROFILE_DIR.glob("*.json")):
            self.list.addItem(f.stem)

    def _selected(self):
        it = self.list.currentItem()
        return it.text() if it else None

    def _new(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New profile", "Name:")
        if ok and name:
            self.app.profile = Profile(name=name)
            self.app.reload_tabs()
            self._write(name)
            self.refresh()

    def _save(self):
        name = self._selected() or self.app.profile.name
        name, ok = QtWidgets.QInputDialog.getText(self, "Save profile", "Name:", text=name)
        if ok and name:
            self.app.collect_tabs()
            self.app.profile.name = name
            self._write(name)
            self.refresh()
            self.app.status(f"Profile '{name}' saved.")

    def _write(self, name):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        (PROFILE_DIR / f"{name}.json").write_text(
            json.dumps(self.app.profile.to_json(), indent=2))

    def _load(self):
        name = self._selected()
        if not name:
            return
        data = json.loads((PROFILE_DIR / f"{name}.json").read_text())
        self.app.profile = Profile.from_json(data)
        self.app.reload_tabs()
        self.app.status(f"Profile '{name}' loaded.")

    def _delete(self):
        name = self._selected()
        if name and QtWidgets.QMessageBox.question(
                self, "Delete", f"Delete '{name}'?") == QtWidgets.QMessageBox.Yes:
            (PROFILE_DIR / f"{name}.json").unlink(missing_ok=True)
            self.refresh()

    def _apply_all(self):
        self._load()
        self.app.apply_everything()

    def _refresh_autostart(self):
        svc = Path.home() / ".config/systemd/user/epomaker-gui.service"
        self.autostart.setText("Service: " + ("installed" if svc.exists() else "not installed"))

    def _install_service(self):
        name = self._selected()
        if not name:
            self.app.status("Select a profile first.")
            return
        d = Path.home() / ".config/systemd/user"
        d.mkdir(parents=True, exist_ok=True)
        script = Path(__file__).resolve().parent / "apply_profile.py"
        (d / "epomaker-gui.service").write_text(f"""[Unit]
Description=Apply EPOMAKER keyboard profile
After=graphical-session.target

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 3
ExecStart={sys.executable} {script} {name}

[Install]
WantedBy=default.target
""")
        self._refresh_autostart()
        self.app.status("Service written. Enable: "
                        "systemctl --user enable --now epomaker-gui.service")


# ---------------------------------------------------------------------------
# Fenetre principale
# ---------------------------------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.profile = self._load_last()

        self.worker = Worker()
        self.worker.done.connect(lambda m: self.status(f"✓ {m}"))
        self.worker.failed.connect(self._on_fail)

        self.effects = EffectsTab(self)
        self.perkey = PerKeyTab(self)
        self.remap = RemapTab(self)
        self.calib = CalibrationTab(self)
        self.screen = ScreenTab(self)
        self.profiles = ProfilesTab(self)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.effects, "Lighting")
        self.tabs.addTab(self.perkey, "Per-key")
        self.tabs.addTab(self.remap, "Remap")
        self.tabs.addTab(self.calib, "Calibration")
        self.tabs.addTab(self.screen, "Screen")
        self.tabs.addTab(self.profiles, "Profiles")

        # -- header ------------------------------------------------------
        self.title = QtWidgets.QLabel()
        self.title.setObjectName("h1")
        self.dot = QtWidgets.QLabel("●")
        self.dev_lbl = QtWidgets.QLabel()
        self.dev_lbl.setObjectName("hint")
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(20, 14, 20, 6)
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.dot)
        header.addWidget(self.dev_lbl)

        central = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addLayout(header)
        v.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.setStatusBar(QtWidgets.QStatusBar())

        self.reload_tabs()
        self._check_device()

    # -- device -----------------------------------------------------------

    def device(self, label, fn):
        self.status(f"… {label}")
        self.worker.run(label, fn)

    def _on_fail(self, msg):
        self.status(msg)
        QtWidgets.QMessageBox.warning(self, "Keyboard error", msg)

    def _check_device(self):
        try:
            path = epomaker.find_hidraw(epomaker.VENDOR_ID, epomaker.PRODUCT_ID,
                                        epomaker.CONFIG_INTERFACE)
            self.dot.setStyleSheet("color: #4caf6a;")
            self.dev_lbl.setText(f"connected · {path}")
        except SystemExit:
            self.dot.setStyleSheet("color: #d1495b;")
            self.dev_lbl.setText("not detected — plug in over USB")

    def status(self, msg):
        self.statusBar().showMessage(msg, 8000)

    # -- profil <-> onglets --------------------------------------------

    def reload_tabs(self):
        self.effects.load(self.profile)
        self.perkey.load(self.profile)
        self.remap.load(self.profile)
        self.title.setText(f"EPOMAKER EA75  ·  {self.profile.name}")

    def collect_tabs(self):
        self.effects.save(self.profile)
        self.perkey.save(self.profile)
        self.remap.save(self.profile)

    def apply_everything(self):
        if self.profile.per_key and self.profile.per_key_enabled:
            self.perkey.apply()
        else:
            self.effects.apply()

    # -- persistance "derniere session" -------------------------------

    def _load_last(self) -> Profile:
        try:
            return Profile.from_json(json.loads(LAST_FILE.read_text()))
        except (OSError, ValueError):
            return Profile()

    def closeEvent(self, e):
        self.collect_tabs()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        LAST_FILE.write_text(json.dumps(self.profile.to_json(), indent=2))
        super().closeEvent(e)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.resize(1120, 620)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
