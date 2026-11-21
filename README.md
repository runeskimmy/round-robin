# Round Robin

Rank anything by having every entry face every other entry. Add images, text, or both, pick a winner in each matchup, and get a real ranking at the end: a ranked list, a tier list, and a grid of every result. It also spots "loops" (A beat B, B beat C, C beat A) and lets you break ties yourself.

Everything stays on your device. Nothing is uploaded anywhere.

## The three versions

| Version | What it is | Where it lives |
|---|---|---|
| Browser | One HTML file that runs offline in any browser | `web/round-robin.html` |
| Windows | A normal installable app (uses the Edge engine built into Windows 10/11) | `windows/` |
| Android | An APK you install yourself (Android 10 or newer) | `android/` |

Each version keeps its own saved data. To move a tournament between them, use **Save file** in one and **Open file** in the other.

## Tests

Every push runs the same checks on GitHub's machines (see `.github/workflows/test.yml`):

- **Web:** plays a full 8-entry tournament in Chrome with a planted loop and a planted tie, then checks the ranking, every results view, saving, copying, tie-breaking, reopening, and restarting.
- **Windows:** installs with the real installer, drives the real app window through the same tournament, closes and reopens it to check your data stays, then uninstalls.
- **Android:** installs the APK on an emulator, adds photos through the real photo picker, plays every matchup, saves files, and tests the back button, reopening, and the restart popup.

Results and screenshots from the latest run are pushed to the `ci-results` branch.

## Building it yourself

- **Browser file:** edit `web/src.html`, then run `python3 web/build.py` (it embeds the fonts so the file works offline).
- **Windows:** `cd windows && cargo build --release`, then build `windows/installer/setup.nsi` with NSIS.
- **Android:** `cd android && ./gradlew assembleDebug`. Release builds are signed only when `RR_KEYSTORE` and `RR_KEY_PASS` are set. The signing key is never stored in this repo.
