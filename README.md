# Round Robin

Rank anything by picking between two at a time. Add images, text, or both, pick a winner in each matchup, and get a real ranking at the end: a ranked list, a tier list, and a grid of every result.

Everything stays on your device. Nothing is uploaded anywhere.

## Download

Get the latest version from the [Releases page](https://github.com/runeskimmy/round-robin/releases/latest).

| You're on | Download | How to install |
|---|---|---|
| Windows 10 or 11 | `RoundRobin-Setup.exe` | Open it and follow the steps. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**. That warning shows up because the installer isn't signed with a paid certificate. |
| Android 10 or newer | `RoundRobin.apk` | Download it on your phone and open it. If your phone asks, allow your browser to install apps. |
| Any computer, no install | `round-robin.html` | Open it in any web browser. It works offline. |

Each version keeps its own saved tournaments. To move one between devices, use **Save file** on one and **Open file** on the other. New versions install over old ones and keep your saved tournaments.

## Ways to play

The app opens as a plain round robin: add entries and press Start. The other styles sit behind a small **Other bracket styles** link, along with a **Which one should I pick?** guide.

| Style | How it works | Best for |
|---|---|---|
| Round robin | Everyone faces everyone once. | The classic. Shows exactly where your picks contradict each other. |
| Round robin+ | A round robin, then a second look at each pair of neighbors in the ranking. Same answer twice settles it; a different answer gets a third look. | Every pair faces off, with close calls double-checked. |
| Sort | Sorts the list like a deck of cards, never asking what earlier picks already answer (if A beat B and B beat C, A goes above C), then double-checks each pair of neighbors. | The most exact ranking for the time. |
| Ask until sure | You choose what to find (your #1, your top few, or everything) and how sure to be (80% to 99%). It gets a rough order, learns how often you flip close calls from the pairs it asks twice, and keeps asking the shakiest pair until it reaches your target. | Being exactly as sure as you want, then stopping. |
| Swiss | Rounds where entries face others with a similar record, never the same pair twice. Can be finished as a full round robin. | A classic chess-style tournament. |
| Top N | Everyone is out after N+1 losses, until the survivors have all faced each other. Then the finalists get second looks. | Your top few, ranked exactly, fast. |
| Double elimination | Out after two losses, with a grand final rematch if needed. | Just your #1. |
| Single elimination | Lose once and you're out, with a 3rd-place match. | Your #1, as fast as possible. |

### How accurate each one is

From thousands of simulated tournaments with 16 entries, played by a chooser who is consistent but flips a close call now and then (about 1 time in 11 between neighbors). Rerun them with `python tools/accuracy.py`.

| Style | Matchups | #1 right | Top 3 in exact order | Whole list exactly right |
|---|---|---|---|---|
| Round robin | 120 | 90% | 71% | 18% |
| Round robin+ | about 139 | 96% | 88% | 57% |
| Sort | about 66 | 98% | 93% | 67% |
| Ask until sure, top 3 at 95% | about 49 | over 99% | 99% | ranks only the top |
| Ask until sure, everything at 95% | about 117 | over 99% | 99% | 96% |
| Swiss | 48 | 89% | 50% | 0% |
| Top 3 | about 58 | 97% | 89% | ranks only the top |
| Double elimination | 30 or 31 | 98% | 63% | 0% |
| Single elimination | 16 | 90% | 24% | 0% |

With perfectly consistent picks, Round robin, Round robin+, Sort, Ask until sure, and Top N get everything they rank exactly right. If you flip close calls very often (about 1 time in 4), Ask until sure's stated sureness about the top few runs a few points optimistic; its "too close to call" flags are the sign.

The app also records how long each pick takes (kept only on your device and in your save files), to test later whether slow picks mean close calls.

### Rank by hand

Next to "Other bracket styles" is **Rank by hand**, for when you'd rather just arrange things yourself. It uses the same entries but never changes a tournament.

- **Tier list:** drag entries from "not ranked yet" into S, A, B, C, and D. Tap a tier's name to rename it.
- **Ordered list:** one numbered list. Drag the handle or use the arrows.
- On a phone, you can also tap an entry and then tap a tier, or hold an entry for a moment to drag it. On a computer, arrow keys move the selected tile.
- Both can be copied as text or saved as an image.

### In the results

- **List, Tiers, and Table** views, plus a bracket picture for the elimination styles.
- **Close-call markers** between neighboring places, from your own picks: "Close call: you picked Pizza over Tacos 2 of 3 times."
- **Loops**, where your picks went in a circle (A beat B, B beat C, C beat A), with a button to redo them.
- **Break the tie** for entries the picks can't separate, plus undo, and saving the ranking as text or an image.

## The three versions (code)

| Version | What it is | Where it lives |
|---|---|---|
| Browser | One HTML file that runs offline in any browser | `web/round-robin.html` |
| Windows | A normal installable app (uses the Edge engine built into Windows 10/11) | `windows/` |
| Android | An APK you install yourself (Android 10 or newer) | `android/` |

## Tests

Every push runs these checks on GitHub's machines (see `.github/workflows/test.yml`):

- **Web:** plays full tournaments in Chrome in every style, with a planted loop, a planted tie, and a second look answered differently on purpose. It checks the rankings, every results view, the guide, the close-call markers, saving, copying, tie-breaking, reopening, and restarting. It also ranks by hand with real mouse drags, taps, and arrow keys, and checks that everything survives a reload.
- **Stress test:** hundreds of simulated tournaments in every style except plain round robin (2 to 40 entries, random and consistent picks, with undo), checking each style's rules and that consistent picks get exact answers in the predicted number of matchups.
- **Windows:** installs with the real installer, drives the real app window through the same tournaments, closes and reopens it to check your data stays, then uninstalls.
- **Android:** installs the APK on an emulator, adds photos through the real photo picker, plays every matchup, uses real taps on the style cards and the guide, saves files, and tests the back button, reopening, and the restart popup.

Results and screenshots from the latest run are pushed to the `ci-results` branch.

## Building it yourself

- **Browser file:** edit `web/src.html`, then run `python3 web/build.py` (it embeds the fonts so the file works offline).
- **Windows:** `cd windows && cargo build --release`, then build `windows/installer/setup.nsi` with NSIS.
- **Android:** `cd android && ./gradlew assembleDebug`. Release builds are signed only when `RR_KEYSTORE` and `RR_KEY_PASS` are set. The signing key is never stored in this repo.
- **Accuracy numbers:** `python tools/accuracy.py [tournaments per row] [noise levels] [entry counts] [styles]`.
