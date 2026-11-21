"""How often does each format get the true 1st, 2nd and 3rd exactly right?

Plays thousands of simulated tournaments through a private copy of the real app, with a chooser
who has a fixed true order and (optionally) sometimes picks the one they really like less, more
often for close calls. Usage: python tools/accuracy.py [tournaments per row] [noise levels]
Noise 0 = perfectly consistent, 0.6 = rarely flips (about 1 in 11 for neighbors), 1.5 = flips close calls (about 1 in 4).
"""
import sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SRC = (Path(__file__).resolve().parent.parent / 'web' / 'round-robin.html').read_text(encoding='utf-8')
COPY = Path(tempfile.gettempdir()) / 'round-robin-accuracy.html'
APP = COPY.as_uri()

SIM = r"""window.__sim = ({ fmt, trials, noise, rounds }) => {
  render = () => {}; save = () => {};          // skip drawing and saving during the simulation
  const truth = id => +S.items.find(i => i.id === id).label.slice(1);   // E00 is truly best
  const out = { first: 0, second: 0, third: 0, top3exact: 0, top3set: 0, matchups: 0, trials };
  for (let t = 0; t < trials; t++) {
    Object.assign(S, { results: {}, history: [], queue: [], tieBreaks: [], rounds: [], bracket: null,
                       format: fmt, swissRounds: rounds || 0, view: 'battle' });
    prepareFormat();
    let m, n = 0;
    while ((m = currentMatch()) && n < 5000) {
      const a = truth(m.a), b = truth(m.b);
      const better = a < b ? 'a' : 'b', worse = better === 'a' ? 'b' : 'a';
      // noise: chance of picking the one you really like less shrinks as the gap grows
      const flip = noise ? 0.5 * Math.exp(-Math.abs(a - b) / noise) : 0;
      pick(Math.random() < flip ? worse : better, true); n++;
    }
    out.matchups += n;
    const rows = ranking().rows;
    const alone = (pos, who) => rows.some(r => r.rank === pos && r.slotSize === 1 && truth(r.id) === who);
    const f = alone(1, 0), s = alone(2, 1), th = alone(3, 2);
    out.first += f; out.second += s; out.third += th; out.top3exact += f && s && th;
    out.top3set += [0, 1, 2].every(w => rows.some(r => truth(r.id) === w && r.rank <= 3));
  }
  return out;
}"""

NOISES = [float(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [0, 1.5]
LABEL = {0: 'consistent    ', 0.6: 'rarely flips  ', 1.5: 'flips close   '}

def main():
    inject = SIM + ";\nwindow.__setup = n => { S = blank(); for (let i = 0; i < n; i++) addItem('E' + String(i).padStart(2, '0'), null); };\n"
    assert SRC.count('window.__rr = {') == 1
    COPY.write_text(SRC.replace('window.__rr = {', inject + 'window.__rr = {'), encoding='utf-8')
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    results = []
    with sync_playwright() as p:
        page = p.chromium.launch().new_page()
        page.goto(APP); page.wait_for_selector('#lines')

        for n in (8, 16, 32):
            page.evaluate("n => window.__setup(n)", n)
            for noise in NOISES:
                for fmt in ('rr', 'swiss', 'single', 'double'):
                    t0 = time.time()
                    r = page.evaluate('a => window.__sim(a)', {'fmt': fmt, 'trials': 1 if (fmt == 'rr' and noise == 0) else trials, 'noise': noise, 'rounds': 0})
                    r.update(n=n, fmt=fmt, noise=noise, secs=round(time.time() - t0, 1))
                    results.append(r)
                    T = r['trials']
                    print(f"n={n:2} {LABEL[noise]} {fmt:6}  "
                          f"1st {100*r['first']/T:5.1f}%  2nd {100*r['second']/T:5.1f}%  3rd {100*r['third']/T:5.1f}%  "
                          f"top3 exact {100*r['top3exact']/T:5.1f}%  top3 set {100*r['top3set']/T:5.1f}%  "
                          f"avg {r['matchups']/T:5.1f} matchups  ({r['secs']}s)", flush=True)

main()
