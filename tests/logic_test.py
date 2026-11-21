"""Logic stress test for Swiss and elimination brackets.

Plays hundreds of simulated tournaments (2 to 40 entries, random or consistent picks, with undo)
through the real app in Chrome, and checks the rules each format must follow.
"""
import os
import random

from playwright.sync_api import sync_playwright

from common import ROOT, main

LETTERS = [f'E{i:02d}' for i in range(60)]  # E00 is the "best" when picks follow a fixed order

PLAY_JS = """async ({ mode, tieRate, undoAt }) => {
  const pref = id => (window.__rr.state().items.find(i => i.id === id) || {}).label;
  let picks = 0, undone = 0;
  for (let guard = 0; guard < 5000; guard++) {
    const m = window.__rr.current();
    if (!m) break;
    let side;
    if (mode === 'prefer') side = pref(m.a) < pref(m.b) ? 'a' : 'b';
    else side = !m.mid && Math.random() < tieRate ? 'tie' : (Math.random() < 0.5 ? 'a' : 'b');
    window.__rr.pick(side);
    picks++;
    if (undoAt && picks === undoAt && undone < 3) {  // take back three picks, then carry on
      for (let u = 0; u < 3; u++) document.querySelector('#undoBtn') && document.querySelector('#undoBtn').click();
      undone = 3;
    }
  }
  return { picks };
}"""


def setup(page, n, fmt, rounds=None):
    if page.query_selector('#newT'):
        page.click('#newT')
        if page.query_selector('#askDlg[open]'):
            page.click('#askOk')
    page.wait_for_selector('#lines')
    page.fill('#lines', '\n'.join(LETTERS[:n]))
    page.click('#addLines')
    page.click(f'[data-format="{fmt}"]')
    if rounds is not None:
        for _ in range(60):
            shown = int(page.inner_text('.fmt-rounds span').split()[0])
            if shown == rounds:
                break
            sel = '[data-rounds="1"]' if shown < rounds else '[data-rounds="-1"]'
            if page.is_disabled(sel):
                break
            page.click(sel)
    page.click('#dockGo')


def body(run):
    url = (ROOT / 'web' / 'round-robin.html').as_uri()
    rng = random.Random(7)
    counts = {'single': 0, 'double': 0, 'swiss': 0}
    fallback_rounds = 0
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome')
        except Exception:  # noqa: BLE001
            browser = p.chromium.launch(executable_path=os.environ.get('CHROME_PATH', '/usr/bin/google-chrome'))
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(url)

        cases = []
        for n in range(2, 41):
            cases.append(('single', n, 'random', 0))
            cases.append(('double', n, 'random', 0))
        for n in [4, 5, 8, 9, 13, 16, 23, 32]:
            cases.append(('single', n, 'prefer', 0))
            cases.append(('double', n, 'prefer', 0))
        for n in [6, 11, 17, 26]:
            cases.append(('double', n, 'random', 5))   # with undo
            cases.append(('single', n, 'random', 4))
        for n in range(2, 31):
            cases.append(('swiss', n, 'random', 0))
        for n in range(3, 13):
            cases.append(('swiss-max', n, 'random', 0))   # every possible round, stressing the pairing
        for n in [7, 12, 20]:
            cases.append(('swiss', n, 'random', 6))        # with undo

        for fmt, n, mode, undo_at in cases:
            real = 'swiss' if fmt.startswith('swiss') else fmt
            setup(page, n, real, rounds=(n - 1) if fmt == 'swiss-max' else None)
            page.evaluate(PLAY_JS, {'mode': mode, 'tieRate': 0.1, 'undoAt': undo_at})
            st = page.evaluate('window.__rr.state()')
            pr = page.evaluate('window.__rr.progress()')
            rows = page.evaluate('window.__rr.ranking()')
            label = {i['id']: i['label'] for i in st['items']}
            tag = f'{fmt} n={n} {mode}{" +undo" if undo_at else ""}'
            ok = pr['complete'] and pr['done'] == pr['total'] and len(rows) == n
            if not ok:
                run.check(False, f'{tag}: finishes with everyone ranked', (pr, len(rows)))
            ranks = [r['rank'] for r in rows]
            if ranks != sorted(ranks) or ranks[0] != 1:
                run.check(False, f'{tag}: ranks are in order', ranks)

            if real in ('single', 'double'):
                br = page.evaluate('window.__rr.bracket()')
                played = len(st['bracket']['results'])
                left = [m for m in br['matches'] if m['status'] in ('ready', 'waiting')]
                if left:
                    run.check(False, f'{tag}: no matches left over', left[:3])
                if rows[0]['id'] != br['champion'] or rows[0]['slotSize'] != 1:
                    run.check(False, f'{tag}: champion is ranked 1st alone', (rows[0], br['champion']))
                losses = {r['id']: r['l'] for r in rows}
                if real == 'single':
                    want = n - 1 + (1 if n >= 4 else 0)
                    if played != want:
                        run.check(False, f'{tag}: {want} matches', played)
                    if sorted(losses.values()).count(2) > (1 if n >= 4 else 0) or losses[br['champion']] != 0:
                        run.check(False, f'{tag}: losses add up', losses)
                else:
                    if played not in (2 * n - 2, 2 * n - 1):
                        run.check(False, f'{tag}: 2n-2 or 2n-1 matches', played)
                    others = [l for i, l in losses.items() if i != br['champion']]
                    if any(l != 2 for l in others) or losses[br['champion']] > 1:
                        run.check(False, f'{tag}: everyone but the champion is out after exactly 2 losses', losses)
                if mode == 'prefer':
                    best = sorted(label, key=lambda i: label[i])
                    if label[br['champion']] != label[best[0]]:
                        run.check(False, f'{tag}: the best entry wins', label[br['champion']])
                    if real == 'double' and (label[rows[1]['id']] != label[best[1]] or played != 2 * n - 2):
                        run.check(False, f'{tag}: the 2nd best finishes 2nd, no rematch needed', (label[rows[1]['id']], played))
                counts[real] += 1
            else:
                seen = set()
                for ri, r in enumerate(st['rounds']):
                    ids = [x for pr_ in r['pairs'] for x in pr_] + r['byes']
                    if len(ids) != len(set(ids)) or len(set(ids)) != n:
                        run.check(False, f'{tag}: round {ri + 1} uses every entry exactly once', r)
                    for a, b in r['pairs']:
                        key = tuple(sorted((a, b)))
                        if key in seen:
                            run.check(False, f'{tag}: no pair meets twice', key)
                        seen.add(key)
                    if len(r['pairs']) < n // 2:
                        fallback_rounds += 1
                import math
                target = (n - 1) if fmt == 'swiss-max' else min(n - 1, math.ceil(math.log2(n)) + 2)
                if len(st['rounds']) != target:
                    run.check(False, f'{tag}: plays all {target} rounds', len(st['rounds']))
                counts['swiss'] += 1
        run.check(True, f"single elimination: {counts['single']} tournaments (2 to 40 entries) follow every rule")
        run.check(True, f"double elimination: {counts['double']} tournaments (2 to 40 entries) follow every rule")
        run.check(True, f"Swiss: {counts['swiss']} tournaments: no repeat pairings, everyone once per round")
        run.log(f'Swiss rounds where a full repeat-free pairing was impossible: {fallback_rounds}')
        run.check(not errors, 'no script errors', errors[:3])
        browser.close()


if __name__ == '__main__':
    main('logic', body)
