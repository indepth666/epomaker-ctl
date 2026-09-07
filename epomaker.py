#!/usr/bin/env python3
"""Controle des fonctions du clavier EPOMAKER / AULA (puce SONiX 0c45:800a).

Cible confirmee sur ce poste : "SONiX AULA EA75MAX" (USB 0c45:800a).
Protocole reconstitue a partir du reverse de parsiya/f108-pro (meme famille SONiX).

Aucune dependance externe : on parle directement au noeud /dev/hidraw de
l'interface 3 (rapports HID "feature" de 64 octets) via les ioctl HIDIOC*.

Utilisation :
    ./epomaker.py probe                       # teste la communication
    ./epomaker.py light static --color ff0000 --brightness 5
    ./epomaker.py light rolling --rainbow --speed 3
    ./epomaker.py off
    ./epomaker.py perkey --color esc=ff0000 --color a=00ff00 --brightness 5
    ./epomaker.py clock                        # regle l'horloge de l'ecran (si present)

ATTENTION : ce clavier ne renvoie jamais son etat courant (protocole write-only).
Le programme officiel garde l'etat dans une base locale. Ici on ne fait qu'ecrire.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

VENDOR_ID = 0x0C45
PRODUCT_ID = 0x800A
CONFIG_INTERFACE = 3   # rapports "feature" 64 o : effets RGB, remap, macros, horloge
LCD_INTERFACE = 2      # rapports "output" 4096 o : image de l'ecran (modeles a ecran)

REPORT_SIZE = 64
CMD_DELAY = 0.035      # 35 ms entre deux commandes (valeur du logiciel officiel)

# ---------------------------------------------------------------------------
# ioctl HIDIOCSFEATURE / HIDIOCGFEATURE
# ---------------------------------------------------------------------------

def _ioc(direction: int, typ: str, nr: int, size: int) -> int:
    op = (direction << 30) | (size << 16) | (ord(typ) << 8) | nr
    # fcntl.ioctl veut un entier signe 32 bits
    if op >= 1 << 31:
        op -= 1 << 32
    return op


_IOC_READ = 2
_IOC_WRITE = 1


def _hidiocsfeature(size: int) -> int:
    return _ioc(_IOC_READ | _IOC_WRITE, "H", 0x06, size)


def _hidiocgfeature(size: int) -> int:
    return _ioc(_IOC_READ | _IOC_WRITE, "H", 0x07, size)


# ---------------------------------------------------------------------------
# Localisation du bon /dev/hidraw
# ---------------------------------------------------------------------------

def _read(path: str) -> str:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def find_hidraw(vid: int, pid: int, interface: int) -> str:
    """Retourne le chemin /dev/hidrawN de l'interface USB demandee."""
    for syspath in glob.glob("/sys/class/hidraw/hidraw*"):
        name = os.path.basename(syspath)
        dev = os.path.realpath(os.path.join(syspath, "device"))
        # dev = .../usb1/1-6/1-6:1.3/0003:0C45:800A.000B/hidraw/hidrawN/../..
        # -> le lien "device" pointe sur le repertoire du peripherique HID
        iface_dir = os.path.dirname(dev)                      # 1-6:1.3
        usb_dir = os.path.dirname(iface_dir)                  # 1-6
        try:
            dev_vid = int(_read(os.path.join(usb_dir, "idVendor")) or "0", 16)
            dev_pid = int(_read(os.path.join(usb_dir, "idProduct")) or "0", 16)
            iface = int(_read(os.path.join(iface_dir, "bInterfaceNumber")) or "-1", 16)
        except ValueError:
            continue
        if dev_vid == vid and dev_pid == pid and iface == interface:
            return f"/dev/{name}"
    raise SystemExit(
        f"Clavier introuvable (VID={vid:04x} PID={pid:04x} interface {interface}).\n"
        "Branche-le en USB (pas en Bluetooth) et verifie `lsusb`."
    )


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

class Keyboard:
    def __init__(self, path: str | None = None, verbose: bool = False):
        self.path = path or find_hidraw(VENDOR_ID, PRODUCT_ID, CONFIG_INTERFACE)
        self.verbose = verbose
        try:
            self.fd = os.open(self.path, os.O_RDWR)
        except PermissionError:
            raise SystemExit(
                f"Pas les droits sur {self.path}.\n"
                "Installe la regle udev fournie (99-epomaker.rules) puis rebranche,\n"
                "ou lance en root pour tester."
            )

    def close(self) -> None:
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- rapports feature -------------------------------------------------

    def _set_feature(self, payload: bytes) -> None:
        import fcntl

        assert len(payload) <= REPORT_SIZE
        buf = bytearray(1 + REPORT_SIZE)          # [report_id=0] + 64 o
        buf[1:1 + len(payload)] = payload
        if self.verbose:
            print("  ->", payload[:16].hex(" "))
        fcntl.ioctl(self.fd, _hidiocsfeature(len(buf)), buf, True)

    def _get_feature(self) -> bytes:
        import fcntl

        buf = bytearray(1 + REPORT_SIZE)
        n = fcntl.ioctl(self.fd, _hidiocgfeature(len(buf)), buf, True)
        data = bytes(buf[:n]) if n > 0 else bytes(buf)
        # retire l'octet report-id de tete si le noyau l'a laisse
        if len(data) == 1 + REPORT_SIZE:
            data = data[1:]
        if self.verbose:
            print("  <-", data[:16].hex(" "))
        return data

    def _cmd(self, payload: bytes, readback: bool = False) -> bytes | None:
        self._set_feature(payload)
        time.sleep(CMD_DELAY)
        if readback:
            resp = self._get_feature()
            time.sleep(CMD_DELAY)
            return resp
        return None

    def _multi(self, data: bytes, readback: bool = False) -> None:
        for off in range(0, len(data), REPORT_SIZE):
            self._set_feature(data[off:off + REPORT_SIZE])
            time.sleep(CMD_DELAY)
        if readback:
            self._get_feature()
            time.sleep(CMD_DELAY)

    # -- primitives de transaction -------------------------------------

    def begin(self):    return self._cmd(b"\x04\x18", readback=True)
    def apply(self):    return self._cmd(b"\x04\x02", readback=True)
    def finalize(self, readback=False): return self._cmd(b"\x04\xF0", readback=readback)

    def _lighting_init(self):
        p = bytearray(REPORT_SIZE)
        p[0], p[1], p[8] = 0x04, 0x13, 0x01
        return self._cmd(p, readback=True)

    # -- fonctionnalites ---------------------------------------------------

    def set_lighting(self, mode: int, r=0, g=0, b=0, brightness=5, speed=3,
                     direction=0, rainbow=False) -> None:
        """Effet global du retroeclairage (20 modes, cf. MODES)."""
        if not 0 <= mode <= 19:
            raise ValueError("mode 0-19")
        for name, v in (("brightness", brightness), ("speed", speed)):
            if not 0 <= v <= 5:
                raise ValueError(f"{name} 0-5")

        self.begin()
        self._lighting_init()

        p = bytearray(REPORT_SIZE)
        p[0] = mode
        if mode != 0:
            p[1], p[2], p[3] = r & 0xFF, g & 0xFF, b & 0xFF
            p[8] = 1 if rainbow else 0
            p[9] = brightness
            p[10] = speed
            p[11] = direction & 1
        p[14], p[15] = 0x55, 0xAA          # trailer (0x55AA LE -> AA 55 sur le fil)
        self._cmd(p, readback=False)

        self.apply()
        self.finalize()

    def off(self) -> None:
        self.set_lighting(0)

    def _led_strip_setup(self, brightness: int) -> None:
        self.begin()
        self._lighting_init()
        d = bytearray(REPORT_SIZE)
        d[0] = 0x80
        d[9] = brightness
        d[14], d[15] = 0x55, 0xAA
        self._cmd(d, readback=False)
        self.apply()
        self.finalize()

    def set_per_key_rgb(self, colors: dict[int, tuple[int, int, int]],
                        brightness: int = 5) -> None:
        """colors : {light_index: (r, g, b)}. Les touches absentes sont eteintes."""
        brightness = max(0, min(5, brightness))
        self._led_strip_setup(brightness)

        self.begin()
        init = bytearray(REPORT_SIZE)
        init[0], init[1], init[8] = 0x04, 0x23, 0x09   # 0x09 = mode RGB
        self._cmd(init, readback=True)

        BUF = 0x240                                    # 576 o = 144 slots x 4
        buf = bytearray(BUF)
        for idx, (r, g, b) in colors.items():
            off = idx * 4
            if idx <= 0 or off + 3 >= BUF - 2:
                continue
            buf[off] = idx & 0xFF
            buf[off + 1] = r & 0xFF
            buf[off + 2] = g & 0xFF
            buf[off + 3] = b & 0xFF
        buf[BUF - 2], buf[BUF - 1] = 0x55, 0xAA
        self._multi(buf, readback=True)

        self.apply()
        self.finalize(readback=True)

    # -- remap de touches -------------------------------------------------

    def set_key_remap(self, slots: dict[int, tuple[int, int, int, int]],
                      fn_layer: bool = False) -> None:
        """Envoie la table de remap complete.

        slots : {key_index: (action, p1, p2, p3)}. key_index absent = touche
        inchangee. action/p1..p3 : voir remap_* plus bas et REMAP_* dans ce
        module. dict vide = reset de la couche.
        """
        self.begin()
        init = bytearray(REPORT_SIZE)
        init[0] = 0x04
        init[1] = 0x27 if fn_layer else 0x11
        init[8] = 0x09
        self._cmd(init, readback=True)

        BUF = 0x240                                    # 576 o = 144 slots x 4
        buf = bytearray(BUF)
        for idx, (action, p1, p2, p3) in slots.items():
            off = idx * 4
            if idx <= 0 or off + 3 >= BUF - 2:
                continue
            buf[off:off + 4] = bytes((action & 0xFF, p1 & 0xFF, p2 & 0xFF, p3 & 0xFF))
        buf[BUF - 2], buf[BUF - 1] = 0xAA, 0x55        # trailer (0x55AA LE) pour le remap
        self._multi(buf, readback=True)

        self.apply()
        self.finalize(readback=True)

    def sync_clock(self, t: time.struct_time | None = None) -> None:
        """Regle l'horloge de l'ecran LCD (modeles a ecran uniquement)."""
        t = t or time.localtime()
        self.begin()
        init = bytearray(REPORT_SIZE)
        init[0], init[1], init[8] = 0x04, 0x28, 0x01
        self._cmd(init, readback=True)

        d = bytearray(REPORT_SIZE)
        d[1] = 0x01                        # profil 1
        d[2] = 0x5A                        # magic
        d[3] = t.tm_year % 2000
        d[4] = t.tm_mon
        d[5] = t.tm_mday
        d[6] = t.tm_hour
        d[7] = t.tm_min
        d[8] = t.tm_sec
        d[10] = (t.tm_wday + 1) % 7        # struct_time : lundi=0 ; clavier : dimanche=0
        d[62], d[63] = 0x55, 0xAA
        self._cmd(d, readback=True)
        self.apply()


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

MODES = {
    "off": 0, "static": 1, "singleon": 2, "singleoff": 3, "glittering": 4,
    "falling": 5, "colourful": 6, "breath": 7, "spectrum": 8, "outward": 9,
    "scrolling": 10, "rolling": 11, "rotating": 12, "explode": 13, "launch": 14,
    "ripples": 15, "flowing": 16, "pulsating": 17, "tilt": 18, "shuttle": 19,
}

# Indices lumineux du F108 Pro (light_index == key_index sur cette famille).
# A verifier / ajuster pour l'EA75MAX (75 %) : les codes ci-dessous couvrent
# le bloc alphanumerique commun.
KEY_INDEX = {
    "esc": 1, "f1": 2, "f2": 3, "f3": 4, "f4": 5, "f5": 6, "f6": 7, "f7": 8,
    "f8": 9, "f9": 10, "f10": 11, "f11": 12, "f12": 13,
    "grave": 19, "1": 20, "2": 21, "3": 22, "4": 23, "5": 24, "6": 25, "7": 26,
    "8": 27, "9": 28, "0": 29, "minus": 30, "equal": 31, "backspace": 103,
    "tab": 37, "q": 38, "w": 39, "e": 40, "r": 41, "t": 42, "y": 43, "u": 44,
    "i": 45, "o": 46, "p": 47, "lbracket": 48, "rbracket": 49, "backslash": 67,
    "capslock": 55, "a": 56, "s": 57, "d": 58, "f": 59, "g": 60, "h": 61,
    "j": 62, "k": 63, "l": 64, "semicolon": 65, "quote": 66, "enter": 85,
    "lshift": 73, "z": 74, "x": 75, "c": 76, "v": 77, "b": 78, "n": 79, "m": 80,
    "comma": 81, "dot": 82, "slash": 83, "rshift": 84, "up": 101,
    "lctrl": 91, "lwin": 92, "lalt": 93, "space": 94, "ralt": 95, "fn": 96,
    "menu": 97, "rctrl": 98, "left": 99, "down": 100, "right": 102,
}


# Codes USB HID (Usage Page 0x07), cible d'un remap "touche".
HID_CODE = {
    "esc": 0x29, "f1": 0x3A, "f2": 0x3B, "f3": 0x3C, "f4": 0x3D, "f5": 0x3E,
    "f6": 0x3F, "f7": 0x40, "f8": 0x41, "f9": 0x42, "f10": 0x43, "f11": 0x44,
    "f12": 0x45, "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48,
    "grave": 0x35, "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27, "minus": 0x2D,
    "equal": 0x2E, "backspace": 0x2A, "insert": 0x49, "home": 0x4A,
    "pageup": 0x4B, "delete": 0x4C, "end": 0x4D, "pagedown": 0x4E,
    "tab": 0x2B, "q": 0x14, "w": 0x1A, "e": 0x08, "r": 0x15, "t": 0x17,
    "y": 0x1C, "u": 0x18, "i": 0x0C, "o": 0x12, "p": 0x13, "lbracket": 0x2F,
    "rbracket": 0x30, "backslash": 0x31,
    "capslock": 0x39, "a": 0x04, "s": 0x16, "d": 0x07, "f": 0x09, "g": 0x0A,
    "h": 0x0B, "j": 0x0D, "k": 0x0E, "l": 0x0F, "semicolon": 0x33, "quote": 0x34,
    "enter": 0x28,
    "lshift": 0xE1, "z": 0x1D, "x": 0x1B, "c": 0x06, "v": 0x19, "b": 0x05,
    "n": 0x11, "m": 0x10, "comma": 0x36, "dot": 0x37, "slash": 0x38,
    "rshift": 0xE5, "up": 0x52,
    "lctrl": 0xE0, "lwin": 0xE3, "lalt": 0xE2, "space": 0x2C, "ralt": 0xE6,
    "menu": 0x65, "rctrl": 0xE4, "left": 0x50, "down": 0x51, "right": 0x4F,
}

# Modificateurs : bit -> code HID de modificateur
MOD_BIT = {0xE0: 0x01, 0xE1: 0x02, 0xE2: 0x04, 0xE3: 0x08,
           0xE4: 0x10, 0xE5: 0x20, 0xE6: 0x40, 0xE7: 0x80}

CONSUMER_CODE = {
    "play": 0xCD, "stop": 0xB7, "prev": 0xB6, "next": 0xB5,
    "volup": 0xE9, "voldown": 0xEA, "mute": 0xE2,
}

MOUSE_PARAMS = {
    "lclick": (0x01, 0x00, 0x00), "rclick": (0x02, 0x00, 0x00),
    "mclick": (0x04, 0x00, 0x00), "scrollup": (0x00, 0x01, 0x00),
    "scrolldn": (0x00, 0xFF, 0x00),
}


def remap_key(target_hid: int, modifiers: int = 0) -> tuple[int, int, int, int]:
    """Slot 'touche' : produit target_hid, avec modificateurs optionnels."""
    if target_hid in MOD_BIT:                 # cible = un modificateur
        return (0x02, MOD_BIT[target_hid] | modifiers, 0x00, 0x00)
    return (0x02, modifiers, target_hid, 0x00)


def remap_consumer(code: int) -> tuple[int, int, int, int]:
    return (0x03, code, 0x00, 0x00)


def remap_mouse(p1: int, p2: int, p3: int) -> tuple[int, int, int, int]:
    return (0x07, p1, p2, p3)


def remap_macro(index: int, loop: int = 1) -> tuple[int, int, int, int]:
    return (0x06, index, loop, 0x00)


def spec_to_slot(spec: dict) -> tuple[int, int, int, int]:
    """Convertit un dict de profil (voir gui.py / apply_profile.py) en slot 4 o.

    spec = {"type": "key"|"combo"|"consumer"|"mouse", ...}
    """
    t = spec["type"]
    if t == "key":
        return remap_key(HID_CODE[spec["key"]])
    if t == "combo":
        mods = 0
        mods |= 0x01 if spec.get("ctrl") else 0
        mods |= 0x02 if spec.get("shift") else 0
        mods |= 0x04 if spec.get("alt") else 0
        mods |= 0x08 if spec.get("win") else 0
        return remap_key(HID_CODE[spec["key"]], mods)
    if t == "consumer":
        return remap_consumer(CONSUMER_CODE[spec["key"]])
    if t == "mouse":
        return remap_mouse(*MOUSE_PARAMS[spec["key"]])
    raise ValueError(f"type de remap inconnu: {t!r}")


def parse_color(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("couleur = RRGGBB en hexa, ex: ff8800")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true", help="trace les paquets HID")
    ap.add_argument("--device", help="chemin /dev/hidraw force")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe", help="teste la communication (begin + readback)")
    sub.add_parser("off", help="eteint le retroeclairage")

    lp = sub.add_parser("light", help="effet global du retroeclairage")
    lp.add_argument("mode", choices=sorted(MODES), help="nom de l'effet")
    lp.add_argument("--color", type=parse_color, default=(255, 255, 255))
    lp.add_argument("--brightness", type=int, default=5)
    lp.add_argument("--speed", type=int, default=3)
    lp.add_argument("--direction", type=int, default=0, choices=(0, 1))
    lp.add_argument("--rainbow", action="store_true", help="arc-en-ciel (ignore --color)")

    pp = sub.add_parser("perkey", help="couleur par touche")
    pp.add_argument("--color", action="append", default=[], metavar="TOUCHE=RRGGBB",
                    help="repetable, ex: --color esc=ff0000 --color a=00ff00")
    pp.add_argument("--brightness", type=int, default=5)

    sub.add_parser("clock", help="regle l'horloge de l'ecran sur l'heure systeme")

    args = ap.parse_args(argv)

    with Keyboard(args.device, verbose=args.verbose) as kb:
        if args.cmd == "probe":
            resp = kb.begin()
            print(f"OK - {kb.path}")
            if resp:
                print("reponse:", resp[:8].hex(" "),
                      "(ACK)" if len(resp) > 3 and resp[3] == 0x01 else "(pas d'ACK ?)")
            kb.finalize()

        elif args.cmd == "off":
            kb.off()
            print("retroeclairage eteint")

        elif args.cmd == "light":
            r, g, b = args.color
            kb.set_lighting(MODES[args.mode], r, g, b,
                            brightness=args.brightness, speed=args.speed,
                            direction=args.direction, rainbow=args.rainbow)
            print(f"effet '{args.mode}' applique")

        elif args.cmd == "perkey":
            colors: dict[int, tuple[int, int, int]] = {}
            for item in args.color:
                key, _, hexval = item.partition("=")
                if key not in KEY_INDEX:
                    raise SystemExit(f"touche inconnue: {key}")
                colors[KEY_INDEX[key]] = parse_color(hexval)
            if not colors:
                raise SystemExit("donne au moins une --color TOUCHE=RRGGBB")
            kb.set_per_key_rgb(colors, brightness=args.brightness)
            print(f"{len(colors)} touche(s) coloree(s)")

        elif args.cmd == "clock":
            kb.sync_clock()
            print("horloge synchronisee")

    return 0


if __name__ == "__main__":
    sys.exit(main())
