"""Shared helpers for the tests: a log file, pass/fail checks, screenshot names, and test images."""
import json
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Run:
    def __init__(self, name):
        self.name = name
        self.dir = ROOT / 'results' / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self._f = open(self.dir / 'log.txt', 'w', encoding='utf-8')
        self.checks = []
        self._shot = 0

    def log(self, *parts):
        line = ' '.join(str(p) for p in parts)
        print(line, flush=True)
        self._f.write(line + '\n')
        self._f.flush()

    def check(self, ok, what, detail=None):
        ok = bool(ok)
        self.checks.append({'ok': ok, 'what': what, 'detail': None if detail is None else str(detail)[:500]})
        self.log(('PASS  ' if ok else 'FAIL  ') + what + ('' if detail is None else f'   [{str(detail)[:300]}]'))
        if not ok:
            raise AssertionError(what)

    def shot(self, name):
        self._shot += 1
        return str(self.dir / f'{self._shot:02d}-{name}.png')

    def finish(self, ok, error=None):
        summary = {'test': self.name, 'ok': ok, 'error': error, 'checks': self.checks}
        (self.dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        passed = sum(c['ok'] for c in self.checks)
        self.log(f'\n{self.name}: {"PASSED" if ok else "FAILED"} ({passed}/{len(self.checks)} checks passed)')
        self._f.close()


def main(name, body):
    """Runs body(run), records the outcome, and exits non-zero on failure."""
    run = Run(name)
    try:
        body(run)
        run.finish(True)
    except Exception as e:  # noqa: BLE001 - we want every failure in the log
        run.log(traceback.format_exc())
        run.finish(False, f'{type(e).__name__}: {e}')
        sys.exit(1)


def make_test_images(folder):
    """Three images: a wide JPG, a tall PNG, and a wide PNG with a screenshot-style name."""
    from PIL import Image, ImageDraw
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    specs = [
        ('IMG_2034.jpg', (230, 90, 70), (800, 600)),
        ('robert-pattinson-haircut.png', (70, 120, 200), (500, 800)),
        ('Screenshot 2026-11-20 at 10.14.22 PM.png', (90, 170, 90), (1200, 700)),
    ]
    paths = []
    for name, color, size in specs:
        im = Image.new('RGB', size, color)
        d = ImageDraw.Draw(im)
        w, h = size
        d.ellipse([w * .25, h * .25, w * .75, h * .75], fill=(250, 240, 200))
        p = folder / name
        im.save(p)
        paths.append(str(p))
    return paths
