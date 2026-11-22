"""Logic stress test for Swiss, Top N, Round robin+ and elimination brackets.

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


ASK_LABEL = {1: 'Your #1', 0: 'Everything'}


def setup(page, n, fmt, rounds=None, top=None, goal=None):
    if page.query_selector('#newT'):
        page.click('#newT')
        if page.query_selector('#askDlg[open]'):
            page.click('#askOk')
    page.wait_for_selector('#lines')
    page.fill('#lines', '\n'.join(LETTERS[:n]))
    page.click('#addLines')
    if not page.query_selector('.fmt-grid'):
        page.click('#moreFmts')
    page.click(f'[data-format="{fmt}"]')
    if top is not None:
        for _ in range(60):
            shown = int(page.inner_text('[data-format="topn"] .step-val').split()[-1])
            if shown == top:
                break
            sel = '[data-topn="1"]' if shown < top else '[data-topn="-1"]'
            if page.is_disabled(sel):
                break
            page.click(sel)
    if goal is not None:
        want = ASK_LABEL.get(goal, f'Top {goal}')
        for _ in range(12):
            shown = page.inner_text('[data-format="ask"] .step-val >> nth=0').strip()
            if shown == want:
                break
            order = ['Your #1', 'Top 2', 'Top 3', 'Top 5', 'Top 10', 'Everything']
            sel = '[data-askgoal="1"]' if order.index(shown) < order.index(want) else '[data-askgoal="-1"]'
            if page.is_disabled(sel):
                break
            page.click(sel)
    if rounds is not None:
        for _ in range(60):
            shown = int(page.inner_text('[data-format="swiss"] .step-val').split()[0])
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
    counts = {'single': 0, 'double': 0, 'swiss': 0, 'rrplus': 0, 'topn': 0, 'sort': 0, 'ask': 0}
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
        for n in range(2, 21):
            cases.append(('rrplus', n, 'random', 0))
        for n in [3, 5, 8, 13, 20]:
            cases.append(('rrplus', n, 'prefer', 0))
        for n, at in [(6, 17), (11, 58)]:
            cases.append(('rrplus', n, 'random', at))      # undo across the switch to second looks
        for top in (1, 2, 3, 5):
            for n in range(2, 31):
                cases.append((f'topn{top}', n, 'random', 0))
            for n in [4, 8, 13, 16, 25]:
                cases.append((f'topn{top}', n, 'prefer', 0))
        for n in [9, 18]:
            cases.append(('topn3', n, 'random', 12))       # with undo
        for n in range(2, 31):
            cases.append(('sort', n, 'random', 0))
        for n in [3, 5, 8, 13, 16, 25, 40]:
            cases.append(('sort', n, 'prefer', 0))
        for n, at in [(7, 6), (12, 40), (20, 70)]:
            cases.append(('sort', n, 'random', at))        # undo while sorting, and during second looks
        for goal in (3, 0):
            for n in range(2, 21):
                cases.append((f'ask{goal}', n, 'random', 0))
        for goal in (1, 3, 0):
            for n in [3, 5, 8, 13, 16, 25]:
                cases.append((f'ask{goal}', n, 'prefer', 0))
        for n, at in [(8, 10), (12, 30)]:
            cases.append(('ask3', n, 'random', at))        # undo during the first pass and during second looks

        for fmt, n, mode, undo_at in cases:
            real = 'swiss' if fmt.startswith('swiss') else 'topn' if fmt.startswith('topn') else 'ask' if fmt.startswith('ask') else fmt
            top = int(fmt[4:]) if real == 'topn' else None
            goal = int(fmt[3:]) if real == 'ask' else None
            setup(page, n, real, rounds=(n - 1) if fmt == 'swiss-max' else None, top=top, goal=goal)
            page.evaluate(PLAY_JS, {'mode': mode, 'tieRate': 0 if real in ('topn', 'sort', 'ask') else 0.1, 'undoAt': undo_at})
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

            if real == 'rrplus':
                check_rrplus(run, tag, n, mode, st, rows, label)
                counts['rrplus'] += 1
            elif real == 'sort':
                check_sort(run, tag, n, mode, st, rows, label)
                counts['sort'] += 1
            elif real == 'ask':
                check_ask(run, tag, n, mode, goal, st, rows, label)
                counts['ask'] += 1
            elif real == 'topn':
                check_topn(run, tag, n, mode, top, st, rows, label)
                counts['topn'] += 1
            elif real in ('single', 'double'):
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
        run.check(True, f"Round robin+: {counts['rrplus']} tournaments: every pair once, every neighbor settled, consistent picks ranked exactly")
        run.check(True, f"Sort: {counts['sort']} tournaments: every neighbor settled, consistent picks ranked exactly in at most n log n matchups")
        run.check(True, f"Ask until sure: {counts['ask']} tournaments: always finishes, no pair asked more than 11 times, consistent picks get the exact answer")
        run.check(True, f"Top N: {counts['topn']} tournaments: no repeats, nobody plays after going out, consistent picks get the exact top N")
        run.log(f'Swiss rounds where a full repeat-free pairing was impossible: {fallback_rounds}')
        run.check(not errors, 'no script errors', errors[:3])
        browser.close()


def pk(a, b):
    return f'{a}|{b}' if a < b else f'{b}|{a}'


def answers(st, k):
    return [st['results'][k]] + st['checks'].get(k, []) if k in st['results'] else []


def is_settled(st, k):
    a = answers(st, k)
    return len(a) >= 3 or (len(a) == 2 and a[0] == a[1])


def check_rrplus(run, tag, n, mode, st, rows, label):
    if len(st['results']) != n * (n - 1) // 2:
        run.check(False, f'{tag}: every pair played once', len(st['results']))
    for k, c in st['checks'].items():
        if not 1 <= len(c) <= 2:
            run.check(False, f'{tag}: no pair asked more than three times', (k, c))
    for x, y in zip(rows, rows[1:]):
        if not is_settled(st, pk(x['id'], y['id'])):
            run.check(False, f'{tag}: every pair of neighbors is settled', (x['id'], y['id']))
    if mode == 'prefer':
        asks = sum(len(c) for c in st['checks'].values())
        order = [label[r['id']] for r in rows]
        if order != sorted(label.values()) or any(r['slotSize'] != 1 for r in rows):
            run.check(False, f'{tag}: consistent picks are ranked exactly', order)
        if asks != n - 1:
            run.check(False, f'{tag}: one second look per neighbor pair', asks)


def merge_worst(n):
    return 0 if n < 2 else merge_worst(n // 2) + merge_worst(n - n // 2) + n - 1


def check_sort(run, tag, n, mode, st, rows, label):
    if sorted(r['rank'] for r in rows) != list(range(1, n + 1)) or any(r['slotSize'] != 1 for r in rows):
        run.check(False, f'{tag}: every entry gets its own place', [r['rank'] for r in rows])
    for k, c in st['checks'].items():
        if not 1 <= len(c) <= 2:
            run.check(False, f'{tag}: no pair asked more than three times', (k, c))
    for x, y in zip(rows, rows[1:]):
        if not is_settled(st, pk(x['id'], y['id'])):
            run.check(False, f'{tag}: every pair of neighbors is settled', (x['id'], y['id']))
    if mode == 'prefer':
        order = [label[r['id']] for r in rows]
        asks = sum(len(c) for c in st['checks'].values())
        if order != sorted(label.values()):
            run.check(False, f'{tag}: consistent picks are ranked exactly', order)
        if asks != n - 1 or len(st['results']) > merge_worst(n):
            run.check(False, f'{tag}: one second look per neighbor pair, sorting in at most {merge_worst(n)}', (asks, len(st['results'])))


def check_ask(run, tag, n, mode, goal, st, rows, label):
    per = {}
    for q in st['asks']:
        k = pk(q['a'], q['b'])
        per[k] = per.get(k, 0) + 1
    if per and max(per.values()) > 11:
        run.check(False, f'{tag}: no pair asked more than 11 times', max(per.values()))
    if mode == 'prefer':
        k = n if goal == 0 or goal >= n else goal
        got = [label[r['id']] for r in rows[:k]]
        if got != sorted(label.values())[:k] or any(r['slotSize'] != 1 for r in rows[:k]):
            run.check(False, f'{tag}: consistent picks get exactly the right answer', got)


def check_topn(run, tag, n, mode, top, st, rows, label):
    N = max(1, min(top, max(1, n - 2)))
    L = max(1, min(N + 1, n - 1))
    losses = {i['id']: 0 for i in st['items']}
    seen = set()
    for ri, r in enumerate(st['rounds']):
        ids = [x for p in r['pairs'] for x in p]
        if len(ids) != len(set(ids)) or set(ids) & set(r['byes']):
            run.check(False, f'{tag}: round {ri + 1} uses each entry at most once', r)
        for a, b in r['pairs']:
            if losses[a] >= L or losses[b] >= L:
                run.check(False, f'{tag}: nobody plays after going out', (ri + 1, a, b, losses[a], losses[b]))
            key = pk(a, b)
            if key in seen:
                run.check(False, f'{tag}: no pair meets twice', key)
            seen.add(key)
        for a, b in r['pairs']:
            w = st['results'].get(pk(a, b))
            if w in (a, b):
                losses[b if w == a else a] += 1
    alive = [i for i, l in losses.items() if l < L]
    out = [i for i, l in losses.items() if l >= L]
    if any(losses[i] != L for i in out):
        run.check(False, f'{tag}: everyone who went out has exactly {L} losses', {i: losses[i] for i in out})
    for i in range(len(alive)):
        for j in range(i + 1, len(alive)):
            if pk(alive[i], alive[j]) not in st['results']:
                run.check(False, f'{tag}: the finalists have all faced each other', (alive[i], alive[j]))
    fin = rows[:len(alive)]
    if set(r['id'] for r in fin) != set(alive):
        run.check(False, f'{tag}: the finalists are ranked first', [r['id'] for r in fin])
    for x, y in zip(fin, fin[1:]):
        if not is_settled(st, pk(x['id'], y['id'])):
            run.check(False, f'{tag}: every pair of neighboring finalists is settled', (x['id'], y['id']))
    if mode == 'prefer':
        want = sorted(label.values())[:L]
        got = [label[r['id']] for r in fin]
        if got != want:
            run.check(False, f'{tag}: the finalists are exactly the real top {L}, in order', (got, want))
        if len(st['results']) != L * (n - L) + L * (L - 1) // 2:
            run.check(False, f'{tag}: exactly the predicted number of matchups', len(st['results']))


if __name__ == '__main__':
    main('logic', body)
