# epomaker-ctl

Linux control tool for **EPOMAKER / AULA** keyboards built on the **SONiX
`0c45:800a`** chip (developed and tested on the *SONiX AULA EA75MAX*) — RGB
effects, per-key color, key remapping and screen clock — without the Windows
software.

- **CLI** (`epomaker.py`) and **headless apply** (`apply_profile.py`): Python
  standard library only, no dependencies.
- **GUI** (`gui.py`): PySide6.

> ⚠️ Unofficial software, provided "as is". The protocol was reverse-engineered.
> See the **Safety** section below.

---

## Install

```sh
git clone https://github.com/hpinet/epomaker-ctl
cd epomaker-ctl

# CLI only: nothing to install (Python >= 3.10)
./epomaker.py probe

# GUI:
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt      # PySide6
python3 gui.py
```

### Non-root access to `/dev/hidraw*`

systemd's `uaccess` ACL is often enough for the local session. Otherwise:

```sh
sudo cp 99-epomaker.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# then re-plug the keyboard
```

The keyboard is located by **VID/PID + interface number**, never by USB port or
`hidrawN` index — any port works, on any machine.

---

## How it works

The keyboard exposes 4 HID interfaces:

| Interface | Role |
|-----------|------|
| 0 | standard key input |
| 1 | media / knob / mouse |
| 2 | LCD screen data (4096-byte output reports) |
| 3 | **configuration** — 64-byte *feature* reports: RGB, remap, clock |

`epomaker-ctl` writes 64-byte HID *feature* reports on interface 3 through the
`HIDIOCSFEATURE` / `HIDIOCGFEATURE` ioctls (no `hidapi`, no `pyusb`).

Every setting is a transaction:
`04 18` (begin) → init → data → `04 02` (apply) → `04 F0` (finalize),
with a `GET_REPORT` read-back after some steps and a **35 ms** delay between
commands.

> **Write-only protocol**: the keyboard never reports its current configuration.
> The CLI/GUI is the source of truth and pushes the desired state.

---

## GUI

```sh
python3 gui.py
```

The UI is in English; source comments and design notes are in French.

| Tab | Purpose | Status |
|-----|---------|--------|
| **Lighting** | global RGB effect + color / brightness / speed / direction / rainbow + preview | ✅ tested |
| **Per-key** | paint each key (left-click paints, right-click clears) | ⚠️ calibrate first |
| **Remap** | reassign keys, normal/Fn layers, combos, media, mouse | ⚠️ calibrate first |
| **Calibration** | lights LEDs one by one to fix the index mapping | tool |
| **Screen** | pushes system time to the keyboard clock (button + 10-min auto-sync) | ✅ tested |
| **Profiles** | save/load JSON configs, "apply on login" systemd service | |

User config lives in `~/.config/epomaker-gui/` (`profiles/*.json`,
`layout_overrides.json`, `last.json`).

### Calibration (required for Per-key and Remap)

Default light indices are taken from the F108 Pro. They should line up on the
alphanumeric block, but **nothing is guaranteed for the EA75MAX**:

1. **Calibration** tab → *Light this index* (turns on a single LED).
2. Click the key that actually lit up → it gets bound to that index.
3. *Next*, repeat → *Save corrections*.

### Persistence across reboot / re-plug

**Profiles** tab → select a profile → *Install "apply on login" service*, then:

```sh
systemctl --user enable --now epomaker-gui.service
```

Or manually: `./apply_profile.py <profile_name>`.

---

## Command line

```sh
./epomaker.py probe                                   # connectivity test
./epomaker.py light static  --color ff0000 --brightness 5
./epomaker.py light rolling --rainbow --speed 3
./epomaker.py light breath  --color 00aaff
./epomaker.py off
./epomaker.py perkey --color esc=ff0000 --color a=00ff00 --brightness 5
./epomaker.py clock                                   # screen clock
./epomaker.py -v light static --color 00ff00          # -v: trace HID packets
```

**Effects:** `off static singleon singleoff glittering falling colourful breath
spectrum outward scrolling rolling rotating explode launch ripples flowing
pulsating tilt shuttle`.

---

## Safety — read before hacking on this

- **Screen image / GIF upload: intentionally not implemented.**
  The SONiX firmware performs no write-bounds checking. On the F108 Pro, an
  over-long GIF **permanently overwrote the on-screen menu graphics** (SPI
  flash, no known recovery). The frame limit only exists in the Windows
  software and is unknown for the EA75MAX. This repo does not ship that
  feature.
- The other operations (RGB, remap, clock) use 64-byte feature reports and
  carry no known risk: worst case an unexpected setting, fixed by the next
  write or an FN reset.
- **2.4 GHz** (`05 10`) and **Bluetooth** modes are not supported — use USB.

---

## Scope

- Built and tested on **SONiX AULA EA75MAX** (`0c45:800a`, 75% layout).
  Likely partially works on other keyboards of the same family (AULA / Epomaker
  / Ajazz on the SONiX `0c45:800a` chip); the layout (`layout_ea75.py`) and the
  indices would need adapting.
- The protocol comes from the reverse-engineering work in
  [`parsiya/f108-pro`](https://github.com/parsiya/f108-pro) (Aula F108 Pro,
  same chip).

## Credits

HID protocol reconstructed from
[`parsiya/f108-pro`](https://github.com/parsiya/f108-pro) by Parsia Hakimian
(MIT license) — Ghidra decompilation of the Aula software plus USB captures.

## License

MIT — see [LICENSE](LICENSE).
