# epomaker-ctl

Contrôle Linux des claviers **EPOMAKER / AULA** à puce **SONiX `0c45:800a`**
(testé sur *SONiX AULA EA75MAX*) — RGB, couleur par touche, remap, horloge de
l'écran — sans passer par le logiciel Windows.

- **CLI** (`epomaker.py`) et **application headless** (`apply_profile.py`) :
  bibliothèque standard Python uniquement, zéro dépendance.
- **Interface graphique** (`gui.py`) : PySide6.

> ⚠️ Logiciel non officiel, fourni « tel quel ». Le protocole a été reconstitué
> par rétro-ingénierie. Voir la section **Sécurité** plus bas.

---

## Installation

```sh
git clone https://github.com/hpinet/epomaker-ctl
cd epomaker-ctl

# CLI seule : rien à installer (Python >= 3.10)
./epomaker.py probe

# GUI :
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt      # PySide6
python3 gui.py
```

### Accès non-root à `/dev/hidraw*`

L'ACL `uaccess` de systemd suffit souvent pour la session locale. Sinon :

```sh
sudo cp 99-epomaker.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# puis rebrancher le clavier
```

Le clavier est retrouvé par **VID/PID + numéro d'interface**, jamais par le port
ou le numéro `hidrawN` : n'importe quel port USB fonctionne.

---

## Comment ça marche

Le clavier expose 4 interfaces HID :

| Interface | Rôle |
|-----------|------|
| 0 | frappe clavier standard |
| 1 | multimédia / molette / souris |
| 2 | données écran LCD (rapports output 4096 o) |
| 3 | **configuration** — rapports *feature* 64 o : RGB, remap, horloge |

`epomaker-ctl` écrit des rapports HID *feature* de 64 octets sur l'interface 3
via les ioctl `HIDIOCSFEATURE` / `HIDIOCGFEATURE` (pas de `hidapi` ni `pyusb`).

Chaque réglage est une transaction :
`04 18` (begin) → init → données → `04 02` (apply) → `04 F0` (finalize),
avec relecture (`GET_REPORT`) après certaines étapes et **35 ms** entre commandes.

> **Protocole write-only** : le clavier ne renvoie jamais sa configuration.
> La CLI/GUI est la source de vérité et repousse l'état voulu.

---

## Interface graphique

```sh
python3 gui.py
```

L'UI est en anglais ; le code et cette doc restent en français.

| Onglet | Rôle | État |
|--------|------|------|
| **Lighting** | effet RGB global + couleur / luminosité / vitesse / direction / arc-en-ciel + aperçu | ✅ testé |
| **Per-key** | peindre chaque touche (clic gauche = peindre, clic droit = effacer) | ⚠️ calibrer d'abord |
| **Remap** | réassigner des touches, couches normale/Fn, combos, multimédia, souris | ⚠️ calibrer d'abord |
| **Calibration** | allume les LED une par une pour corriger le mapping des index | outil |
| **Screen** | pousse l'heure système sur l'écran (bouton + auto-sync 10 min) | ✅ testé |
| **Profiles** | sauver/charger des configs JSON, service systemd « appliquer au démarrage » | |

Config utilisateur : `~/.config/epomaker-gui/` (`profiles/*.json`,
`layout_overrides.json`, `last.json`).

### Calibration (indispensable pour Per-key et Remap)

Les index lumineux par défaut viennent du F108 Pro. Sur le bloc alphanumérique
ils devraient coïncider, mais **rien n'est garanti pour l'EA75MAX** :

1. Onglet **Calibration** → *Light this index* (n'allume qu'une LED).
2. Clique la touche réellement allumée → elle est liée à cet index.
3. *Next*, etc. → *Save corrections*.

### Persistance après reboot / débranchement

Onglet **Profiles** → sélectionne un profil → *Install "apply on login" service*,
puis :

```sh
systemctl --user enable --now epomaker-gui.service
```

Ou à la main : `./apply_profile.py <nom_profil>`.

---

## Ligne de commande

```sh
./epomaker.py probe                                   # test de communication
./epomaker.py light static  --color ff0000 --brightness 5
./epomaker.py light rolling --rainbow --speed 3
./epomaker.py light breath  --color 00aaff
./epomaker.py off
./epomaker.py perkey --color esc=ff0000 --color a=00ff00 --brightness 5
./epomaker.py clock                                   # horloge de l'écran
./epomaker.py -v light static --color 00ff00          # -v : trace les paquets
```

**Effets :** `off static singleon singleoff glittering falling colourful breath
spectrum outward scrolling rolling rotating explode launch ripples flowing
pulsating tilt shuttle`.

---

## Sécurité — à lire avant de bidouiller

- **Upload d'image / GIF sur l'écran : non implémenté, volontairement.**
  Le firmware SONiX ne vérifie aucune borne d'écriture. Sur le F108 Pro, un GIF
  trop long a **écrasé définitivement les graphismes des menus** (flash SPI,
  aucune récupération connue). La limite de frames n'existe que dans le logiciel
  Windows et est inconnue pour l'EA75MAX. Ce dépôt ne fournit pas cette
  fonction.
- Les autres opérations (RGB, remap, horloge) passent par des rapports *feature*
  de 64 o et sont sans risque connu : au pire un réglage inattendu, corrigé au
  réglage suivant ou par un reset FN.
- Modes **2.4 GHz** (`05 10`) et **Bluetooth** : non gérés — utiliser l'USB.

---

## Portée

- Développé et testé sur **SONiX AULA EA75MAX** (`0c45:800a`, format 75 %).
  Devrait fonctionner en partie sur les autres claviers de la même famille
  (AULA / Epomaker / Ajazz à puce SONiX `0c45:800a`) ; la disposition
  (`layout_ea75.py`) et les index sont à adapter.
- Le protocole vient de la rétro-ingénierie de
  [`parsiya/f108-pro`](https://github.com/parsiya/f108-pro) (Aula F108 Pro,
  même puce).

## Crédits

Protocole HID reconstitué à partir de
[`parsiya/f108-pro`](https://github.com/parsiya/f108-pro) de Parsia Hakimian
(licence MIT) — décompilation Ghidra du logiciel Aula + captures USB.

## Licence

MIT — voir [LICENSE](LICENSE).
