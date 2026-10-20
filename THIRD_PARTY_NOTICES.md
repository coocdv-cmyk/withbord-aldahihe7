# Third-Party Notices

This project (`rasm-pro` / `withbord-aldahihe7`) is distributed under the MIT
License (see `LICENSE`). The components below are **not** covered by that
license; they keep their own terms. The audit that produced this file is
`rasm-pro/docs/10-LICENSE-AUDIT-AR.md` (verified 2026-10-20 on this machine).

Everything listed here is either (a) redistributed inside the repository, or
(b) used locally without being redistributed. The table states which.

## 1. Redistributed inside this repository

### Fonts — `rasm-pro/assets/fonts/`

| Item | License | Where the license text lives |
|---|---|---|
| 38 font families (alexandria … tajawal) | SIL Open Font License 1.1 | `assets/fonts/<family>/OFL.txt` (shipped with each family) |
| `specialelite` (Special Elite) | Apache License 2.0 | `assets/fonts/specialelite/LICENSE.txt` |

The fonts are shipped unmodified, with their license file next to them, as the
OFL and Apache-2.0 require. OFL permits embedding in rendered images and
videos; the fonts are not sold on their own.

### Project source

All first-party code under `rasm-pro/`, `studio/`, `tools/` and `tests/` is
MIT-licensed (see `LICENSE`).

### Icon library metadata

`rasm-pro/library/manifest-icons.jsonl` is a **manifest** (paths, SHA-256,
license per entry) that describes icons this project can download from public
collections. The icons themselves are not committed; they are fetched from
their original sources. Per-collection licenses are recorded in
`rasm-pro/library/stats.json` and per-icon in the manifest. Where a collection
requires attribution (for example CC-BY-4.0), the generated
`projects/<id>/research/CREDITS.md` carries the attribution and must travel
with any project that uses those icons.

## 2. Used locally, not redistributed

| Component | Version | License | Notes |
|---|---|---|---|
| Qwen3-4B-Instruct-2507 (GGUF) | 2507 | Apache-2.0 | Model weights stay on this machine (`studio/models/`), are never uploaded, and are not part of any package. |
| ffmpeg / ffprobe | 9.0.2 (gyan.dev full build) | **GPL-3.0-or-later** (built `--enable-gpl --enable-version3`) | Deliberately **not bundled**. It is an external `sidecar` the user provides. Anyone redistributing this project must not include this binary; if they redistribute a GPL ffmpeg build they take on GPLv3 obligations for that binary. |
| PyInstaller | 6.22.3 | GPL-2.0-or-later **with the bootloader exception** | Only used to build. The produced application is not a GPL work because of the bootloader exception, and PyInstaller itself is not distributed. |
| jsonschema | 4.26.0 | MIT | Verification-only tool used outside the app to cross-check the JSON Schemas; not a runtime dependency. |

## 3. Runtime Python dependencies

Read from the local `.venv` metadata on 2026-10-20. All are permissive and
MIT-compatible.

| Package | Version | License |
|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib |
| pillow | 13.0.0 | MIT-CMU |
| requests | 2.34.2 | Apache-2.0 |
| uharfbuzz | 0.56.3 | Apache-2.0 |
| fonttools | 4.67.0 | MIT |
| svgelements | 1.9.6 | MIT |
| shapely | 2.2.0 | BSD-3-Clause |
| pyclipper | 1.4.0 | MIT |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 |
| scikit-image | 0.26.0 | BSD-3-Clause |
| scipy | 1.18.1 | BSD-3-Clause |
| ImageIO | 2.38.1 | BSD-2-Clause |
| tifffile | 2026.10.15 | BSD-3-Clause |
| networkx | 3.7 | BSD-3-Clause |
| certifi | 2026.7.22 | MPL-2.0 |
| charset-normalizer | 3.5.2 | MIT |
| idna | 3.20 | BSD-3-Clause |
| urllib3 | 2.8.0 | MIT |
| colorama | 0.4.6 | BSD-3-Clause |
| pytest (dev) | 9.1.1 | MIT |
| pluggy (dev) | 1.7.0 | MIT |
| iniconfig (dev) | 2.3.1 | MIT |
| Pygments (dev) | 2.21.0 | BSD-2-Clause |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| lazy-loader | 0.6 | BSD-3-Clause |
| pip | 26.2.1 | MIT |

## 4. Assets retrieved per project

Assets downloaded for a project (for example from Wikimedia Commons) keep their
own licenses. The project manifest (`projects/<id>/project.json`) records for
every asset its `origin` (source + URL), `license`, `license_url`, author and
attribution requirement, and its human approval state. Generated artwork is
**never** treated as historical evidence. Any project released publicly must
ship the attribution file produced with it
(`projects/<id>/research/CREDITS.md`).
