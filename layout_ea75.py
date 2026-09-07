"""Disposition physique de l'EPOMAKER / AULA EA75 (MAX) — format 75 %.

Chaque touche : (label, id, largeur_en_U, code_hid, key_index).

- `id`          : identifiant stable (sert de cle dans les profils JSON).
- `code_hid`    : nom dans epomaker.HID_CODE (comportement par defaut de la touche).
- `key_index`   : index interne du firmware (== light_index sur cette famille).
                  Repris du F108 Pro ; a confirmer via l'onglet "Calibration"
                  de la GUI. `None` = inconnu (ex : molette).

`GAP` insere un espace horizontal (en U) sans touche.
"""

GAP = ("__gap__", None, 0, None, None)


def gap(width):
    return ("__gap__", None, width, None, None)


# (label, id, largeur U, nom HID, key_index)
ROWS = [
    # --- Rangee 0 : fonctions + molette -------------------------------------
    [
        ("Esc", "esc", 1, "esc", 1),
        gap(0.5),
        ("F1", "f1", 1, "f1", 2), ("F2", "f2", 1, "f2", 3),
        ("F3", "f3", 1, "f3", 4), ("F4", "f4", 1, "f4", 5),
        gap(0.25),
        ("F5", "f5", 1, "f5", 6), ("F6", "f6", 1, "f6", 7),
        ("F7", "f7", 1, "f7", 8), ("F8", "f8", 1, "f8", 9),
        gap(0.25),
        ("F9", "f9", 1, "f9", 10), ("F10", "f10", 1, "f10", 11),
        ("F11", "f11", 1, "f11", 12), ("F12", "f12", 1, "f12", 13),
        gap(0.25),
        ("Del", "delete", 1, "delete", 119),
        gap(0.25),
        ("Knob", "knob", 1, None, None),
    ],
    # --- Rangee 1 : chiffres ----------------------------------------------
    [
        ("`", "grave", 1, "grave", 19),
        ("1", "1", 1, "1", 20), ("2", "2", 1, "2", 21), ("3", "3", 1, "3", 22),
        ("4", "4", 1, "4", 23), ("5", "5", 1, "5", 24), ("6", "6", 1, "6", 25),
        ("7", "7", 1, "7", 26), ("8", "8", 1, "8", 27), ("9", "9", 1, "9", 28),
        ("0", "0", 1, "0", 29), ("-", "minus", 1, "minus", 30),
        ("=", "equal", 1, "equal", 31),
        ("Backspace", "backspace", 2, "backspace", 103),
        gap(0.25),
        ("Home", "home", 1, "home", 117),
    ],
    # --- Rangee 2 : AZERTY/QWERTY ---------------------------------------
    [
        ("Tab", "tab", 1.5, "tab", 37),
        ("Q", "q", 1, "q", 38), ("W", "w", 1, "w", 39), ("E", "e", 1, "e", 40),
        ("R", "r", 1, "r", 41), ("T", "t", 1, "t", 42), ("Y", "y", 1, "y", 43),
        ("U", "u", 1, "u", 44), ("I", "i", 1, "i", 45), ("O", "o", 1, "o", 46),
        ("P", "p", 1, "p", 47), ("[", "lbracket", 1, "lbracket", 48),
        ("]", "rbracket", 1, "rbracket", 49),
        ("\\", "backslash", 1.5, "backslash", 67),
        gap(0.25),
        ("PgUp", "pageup", 1, "pageup", 118),
    ],
    # --- Rangee 3 : home row ------------------------------------------------
    [
        ("Caps", "capslock", 1.75, "capslock", 55),
        ("A", "a", 1, "a", 56), ("S", "s", 1, "s", 57), ("D", "d", 1, "d", 58),
        ("F", "f", 1, "f", 59), ("G", "g", 1, "g", 60), ("H", "h", 1, "h", 61),
        ("J", "j", 1, "j", 62), ("K", "k", 1, "k", 63), ("L", "l", 1, "l", 64),
        (";", "semicolon", 1, "semicolon", 65),
        ("'", "quote", 1, "quote", 66),
        ("Enter", "enter", 2.25, "enter", 85),
        gap(0.25),
        ("PgDn", "pagedown", 1, "pagedown", 121),
    ],
    # --- Rangee 4 : shift -------------------------------------------------
    [
        ("Shift", "lshift", 2.25, "lshift", 73),
        ("Z", "z", 1, "z", 74), ("X", "x", 1, "x", 75), ("C", "c", 1, "c", 76),
        ("V", "v", 1, "v", 77), ("B", "b", 1, "b", 78), ("N", "n", 1, "n", 79),
        ("M", "m", 1, "m", 80), (",", "comma", 1, "comma", 81),
        (".", "dot", 1, "dot", 82), ("/", "slash", 1, "slash", 83),
        ("Shift", "rshift", 1.75, "rshift", 84),
        ("Up", "up", 1, "up", 101),
        gap(0.25),
        ("End", "end", 1, "end", 120),
    ],
    # --- Rangee 5 : bas ---------------------------------------------------
    [
        ("Ctrl", "lctrl", 1.25, "lctrl", 91),
        ("Win", "lwin", 1.25, "lwin", 92),
        ("Alt", "lalt", 1.25, "lalt", 93),
        ("Space", "space", 6.25, "space", 94),
        ("Alt", "ralt", 1, "ralt", 95),
        ("Fn", "fn", 1, "fn", 96),
        ("Ctrl", "rctrl", 1, "rctrl", 98),
        ("Left", "left", 1, "left", 99),
        ("Down", "down", 1, "down", 100),
        ("Right", "right", 1, "right", 102),
    ],
]


def iter_keys():
    """Genere (row, x_en_U, key) pour chaque vraie touche (hors GAP)."""
    for r, row in enumerate(ROWS):
        x = 0.0
        for label, kid, w, hid, index in row:
            if label == "__gap__":
                x += w
                continue
            yield r, x, (label, kid, w, hid, index)
            x += w


def default_index_map():
    """{id_touche: key_index} d'apres le F108 Pro (a calibrer)."""
    return {k[1]: k[4] for _, _, k in iter_keys() if k[4] is not None}


def key_by_id():
    return {k[1]: k for _, _, k in iter_keys()}
