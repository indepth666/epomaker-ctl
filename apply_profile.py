#!/usr/bin/env python3
"""Applique un profil de la GUI au clavier, sans interface.

    ./apply_profile.py <nom_profil>
    ./apply_profile.py ~/.config/epomaker-gui/profiles/mon_profil.json

Utilise par le service systemd « epomaker-gui.service » pour restaurer la
configuration apres un branchement / redemarrage.
"""

import json
import sys
import time
from pathlib import Path

import epomaker
import layout_ea75

CONFIG_DIR = Path.home() / ".config" / "epomaker-gui"


def load_profile(arg: str) -> dict:
    p = Path(arg)
    if not p.exists():
        p = CONFIG_DIR / "profiles" / f"{arg}.json"
    return json.loads(p.read_text())


def index_map() -> dict:
    m = layout_ea75.default_index_map()
    try:
        ov = json.loads((CONFIG_DIR / "layout_overrides.json").read_text())
        m.update({k: int(v) for k, v in ov.items()})
    except (OSError, ValueError):
        pass
    return m


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    prof = load_profile(sys.argv[1])
    imap = index_map()

    with epomaker.Keyboard() as kb:
        if prof.get("per_key") and prof.get("per_key_enabled"):
            colors = {imap[k]: tuple(v) for k, v in prof["per_key"].items()
                      if k in imap}
            kb.set_per_key_rgb(colors, brightness=prof.get("per_key_brightness", 5))
        else:
            r, g, b = prof.get("color", [255, 255, 255])
            kb.set_lighting(epomaker.MODES[prof.get("effect", "static")], r, g, b,
                            brightness=prof.get("brightness", 5),
                            speed=prof.get("speed", 3),
                            direction=prof.get("direction", 0),
                            rainbow=prof.get("rainbow", False))

        for layer_name, fn in (("normal", False), ("fn", True)):
            specs = (prof.get("remap") or {}).get(layer_name) or {}
            if not specs:
                continue
            slots = {imap[k]: epomaker.spec_to_slot(s) for k, s in specs.items()
                     if k in imap}
            time.sleep(0.1)
            kb.set_key_remap(slots, fn_layer=fn)

    print("profil applique")
    return 0


if __name__ == "__main__":
    sys.exit(main())
