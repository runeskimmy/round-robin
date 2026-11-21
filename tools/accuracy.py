"""How often does each format get your real 1st, 2nd and 3rd exactly right?

Plays thousands of simulated tournaments through a private copy of the real app. The chooser has a
fixed true order and, depending on the noise level, sometimes picks the one they really like less,
more often for close calls (noise 0 = perfectly consistent, 0.6 = rarely flips, about 1 in 11 for
neighbors, 1.5 = often flips close calls, about 1 in 4).

Usage: python tools/accuracy.py [tournaments per row] [noise levels] [entry counts] [formats]
Formats: rr, rrplus, sort, swiss, single, double, topn:N:spare  (e.g. topn:3:1 = top 3 with one spare life),
         ask:goal:sure[:a/b flip-rate prior[:maxPair]]  (e.g. ask:3:95 = Ask until sure, top 3, 95% sure; goal 0 = the whole order)
"""
import sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SRC = (Path(__file__).resolve().parent.parent / 'web' / 'round-robin.html').read_text(encoding='utf-8')
COPY = Path(tempfile.gettempdir()) / 'round-robin-accuracy.html'
LABEL = {0: 'consistent', 0.6: 'rarely flips', 1.5: 'often flips'}

SIM = r"""window.__sim = ({ fmt, trials, noise, topN, spare, sure, prior, maxPair, extra, rel, pairC }) => {
  render = () => {}; save = () => {};          // skip drawing and saving during the simulation
  if (spare !== undefined) TOP_SPARE = spare;
  if (prior) { ASK_EPS_A = prior[0]; ASK_EPS_B = prior[1]; }
  if (maxPair) ASK_MAX_PAIR = maxPair;
  if (extra) ASK_EXTRA = extra;
  if (rel !== undefined) ASK_REL = rel;
  if (pairC) ASK_PAIR_C = pairC;
  const truth = id => +S.items.find(i => i.id === id).label.slice(1);   // E00 is truly best
  const out = { flagged: 0, fair: 0, short: 0, first: 0, second: 0, third: 0, top3exact: 0, top3set: 0, topNexact: 0, full: 0, off: 0, matchups: 0, trials };
  const n = S.items.length;
  for (let t = 0; t < trials; t++) {
    Object.assign(S, { results: {}, history: [], queue: [], tieBreaks: [], rounds: [], bracket: null, checks: {}, sortSeed: [], askSeed: [], asks: [], askGoal: topN === undefined ? 3 : topN, askSure: sure || 95,
                       format: fmt, swissRounds: 0, topN: topN || 3, view: 'battle' });
    prepareFormat();
    let m, k = 0;
    while ((m = currentMatch()) && k < 20000) {
      const a = truth(m.a), b = truth(m.b);
      const better = a < b ? 'a' : 'b', worse = better === 'a' ? 'b' : 'a';
      const flip = noise ? 0.5 * Math.exp(-Math.abs(a - b) / noise) : 0;
      pick(Math.random() < flip ? worse : better, true); k++;
    }
    out.matchups += k;
    const rows = ranking().rows;
    const alone = (pos, who) => rows.some(r => r.rank === pos && r.slotSize === 1 && truth(r.id) === who);
    const f = alone(1, 0), s = alone(2, 1), th = alone(3, 2);
    out.first += f; out.second += s; out.third += th; out.top3exact += f && s && th;
    out.top3set += [0, 1, 2].every(w => rows.some(r => truth(r.id) === w && r.rank <= 3));
    const N = topN || n;
    out.topNexact += Array.from({ length: N }, (_, i) => alone(i + 1, i)).every(Boolean);
    out.full += rows.every(r => r.slotSize === 1 && r.rank === truth(r.id) + 1);
    if (fmt === 'ask') {  // right once pairs it openly called too close to call are allowed to go either way?
      const md = askModel(), KK = askGoalOf(n), seq = rows.map(r => r.id);
      for (let pass = 0; pass < seq.length; pass++) for (let p = 0; p + 1 < seq.length; p++)
        if (md.tooClose.has(pk(seq[p], seq[p + 1])) && truth(seq[p]) > truth(seq[p + 1])) [seq[p], seq[p + 1]] = [seq[p + 1], seq[p]];
      out.flagged += md.tooClose.size > 0;
      out.short += md.stopped;
      out.fair += seq.slice(0, KK).every((id, i) => truth(id) === i);
    }
    out.off += rows.reduce((x, r) => x + Math.abs(r.rank + (r.slotSize - 1) / 2 - 1 - truth(r.id)), 0) / n;
  }
  return out;
}"""


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    noises = [float(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [0, 0.6, 1.5]
    sizes = [int(x) for x in sys.argv[3].split(',')] if len(sys.argv) > 3 else [8, 16, 32]
    fmts = sys.argv[4].split(',') if len(sys.argv) > 4 else ['rr', 'rrplus', 'sort', 'swiss', 'topn:3:1', 'double', 'single']
    inject = SIM + ";\nwindow.__setup = n => { S = blank(); for (let i = 0; i < n; i++) addItem('E' + String(i).padStart(2, '0'), null); };\n"
    assert SRC.count('window.__rr = {') == 1
    COPY.write_text(SRC.replace('window.__rr = {', inject + 'window.__rr = {'), encoding='utf-8')
    with sync_playwright() as p:
        page = p.chromium.launch().new_page()
        page.goto(COPY.as_uri()); page.wait_for_selector('#lines')
        for n in sizes:
            page.evaluate("n => window.__setup(n)", n)
            for noise in noises:
                for spec in fmts:
                    parts = spec.split(':')
                    arg = {'fmt': parts[0], 'trials': 1 if (parts[0] == 'rr' and noise == 0) else trials, 'noise': noise}
                    if parts[0] == 'topn':
                        arg['topN'] = int(parts[1]); arg['spare'] = int(parts[2])
                    if parts[0] == 'ask':  # ask:goal:sure[:prior[:maxPair]]  goal 0 = the whole order
                        arg['topN'] = int(parts[1]); arg['sure'] = int(parts[2])
                        if len(parts) > 3: arg['prior'] = [float(x) for x in parts[3].split('/')]
                        if len(parts) > 4: arg['maxPair'] = int(parts[4])
                        if len(parts) > 5: arg['extra'] = int(parts[5])
                        if len(parts) > 6: arg['rel'] = int(parts[6])
                        if len(parts) > 7: arg['pairC'] = float(parts[7])
                    t0 = time.time()
                    r = page.evaluate('a => window.__sim(a)', arg)
                    T = r['trials']; pc = lambda x: f"{100 * r[x] / T:5.1f}%"
                    print(f"n={n:2} {LABEL.get(noise, noise):12} {spec:9} 1st {pc('first')} 2nd {pc('second')} 3rd {pc('third')} "
                          f"top3 exact {pc('top3exact')} top3 group {pc('top3set')} topN exact {pc('topNexact')} "
                          f"all exact {pc('full')} places off {r['off'] / T:4.2f}  " + (f"flagged {pc('flagged')} stopped-short {pc('short')} fair-right {pc('fair')}  " if spec.startswith('ask') else '') + f"avg {r['matchups'] / T:6.1f} matchups ({time.time() - t0:.1f}s)", flush=True)


main()
