"""The full tournament run, written once and used by both the browser test and the Windows app test.

It plays 8 entries (5 typed, 3 images) through all 28 matchups using a hidden "true" order,
plus one deliberate loop (Tacos > Image 1 > Sushi > Tacos) and one deliberate tie (Pizza vs Burgers),
then checks the ranking, every results view, saving, copying, and tie-breaking.
"""
import json

PREF = ['Ramen', 'robert pattinson haircut', 'Sushi', 'Image 1', 'Tacos', 'Image 2', 'Pizza', 'Burgers']
LOOP = {frozenset(['Sushi', 'Image 1']): 'Image 1', frozenset(['Image 1', 'Tacos']): 'Tacos'}
TIE = frozenset(['Pizza', 'Burgers'])
WHOLE_IMAGES_JS = """sel => [...document.querySelectorAll(sel)].every(i =>
  i.getBoundingClientRect().height <= i.parentElement.getBoundingClientRect().height + 0.5 &&
  i.getBoundingClientRect().width <= i.parentElement.getBoundingClientRect().width + 0.5)"""


def _wait_progress_change(page, before):
    page.wait_for_function(
        "b => { const el = document.querySelector('.progress-txt b'); return !el || el.textContent !== b; }",
        arg=before, timeout=8000)


def add_entries(page, run, images):
    page.wait_for_selector('#lines', timeout=30000)
    page.fill('#lines', 'Pizza\nTacos\n\nRamen\nSushi\nBurgers')
    page.click('#addLines')
    page.set_input_files('#imgIn', images)
    page.wait_for_function("document.querySelectorAll('.tile').length === 8", timeout=30000)
    labels = page.eval_on_selector_all('.tile-name', 'els => els.map(e => e.value)')
    run.check(labels == ['Pizza', 'Tacos', 'Ramen', 'Sushi', 'Burgers', '', 'robert pattinson haircut', ''],
              'typed and image entries added; camera-style file names left blank', labels)
    run.check(page.evaluate(WHOLE_IMAGES_JS, '.tile-face img'), 'entry previews show whole images')
    dock = page.inner_text('.dock p')
    run.check('28 matchups' in dock, 'bottom bar shows 28 matchups for 8 entries', dock)
    page.screenshot(path=run.shot('entries'), full_page=True)


def play_all(page, run):
    page.click('#dockGo')
    page.wait_for_selector('.fighter', timeout=10000)
    page.screenshot(path=run.shot('matchup'))
    first = page.inner_text('.progress-txt b')
    page.keyboard.press('ArrowLeft')
    _wait_progress_change(page, first)
    page.keyboard.press('z')
    page.wait_for_function("t => document.querySelector('.progress-txt b').textContent === t", arg=first, timeout=8000)
    run.check(True, 'keyboard pick, then Z undoes it', first)

    n, prev, repeats = 0, None, 0
    while page.query_selector('.fighter'):
        a = page.get_attribute('.fighter[data-side="a"]', 'aria-label')[5:]
        b = page.get_attribute('.fighter[data-side="b"]', 'aria-label')[5:]
        pair = frozenset([a, b])
        if prev and prev & pair:
            repeats += 1
        prev = pair
        if pair == TIE:
            key = 'ArrowDown'
        elif pair in LOOP:
            key = 'ArrowLeft' if LOOP[pair] == a else 'ArrowRight'
        else:
            key = 'ArrowLeft' if PREF.index(a) < PREF.index(b) else 'ArrowRight'
        if n == 10:
            page.screenshot(path=run.shot('matchup-mid'))
        before = page.inner_text('.progress-txt b')
        page.keyboard.press(key)
        _wait_progress_change(page, before)
        n += 1
        if n > 40:
            break
    run.check(n == 28, 'played all 28 matchups', n)
    run.check(repeats == 0, 'no entry showed up twice in a row', repeats)


def ranking(page):
    return page.eval_on_selector_all(
        '.row', 'els => els.map(e => [e.querySelector(".rank").textContent.trim(), e.querySelector(".name").textContent.trim()])')


def check_results(page, run, save):
    """save(page, selector, filename) clicks the button and returns the saved file's path."""
    page.wait_for_selector('.res-head h2', timeout=10000)
    run.check(page.inner_text('.res-head h2') == 'Final ranking', 'final ranking screen')
    rows = ranking(page)
    run.check(rows[:2] == [['1', 'Ramen'], ['2', 'robert pattinson haircut']], 'top two match the hidden order', rows)
    run.check(sorted(r[1] for r in rows[2:5]) == ['Image 1', 'Sushi', 'Tacos'] and all(r[0] == '3' for r in rows[2:5]),
              'the planted loop shows up as a 3-way tie for 3rd', rows[2:5])
    run.check(rows[5] == ['6', 'Image 2'], '6th place', rows[5])
    run.check(sorted(r[1] for r in rows[6:]) == ['Burgers', 'Pizza'] and all(r[0] == '7' for r in rows[6:]),
              'the planted tie shows up as a 2-way tie for 7th', rows[6:])
    loops = page.inner_text('.loops summary')
    run.check('95% consistent' in loops and '1 loop' in loops, 'loop detector finds exactly the planted loop', loops)
    run.check(page.evaluate(WHOLE_IMAGES_JS, '.th img'), 'ranking thumbnails show whole images')
    page.screenshot(path=run.shot('ranking'), full_page=True)

    page.click('[data-tab="tiers"]')
    run.check(len(page.query_selector_all('.tier')) == 5, 'tiers view has S through D')
    run.check(page.evaluate(WHOLE_IMAGES_JS, '.tt-box img'), 'tier tiles show whole images')
    page.screenshot(path=run.shot('tiers'), full_page=True)
    p = save(page, '#saveImg', 'export-tiers.png')
    run.check(p and open(p, 'rb').read(8) == b'\x89PNG\r\n\x1a\n', 'Save as image (tiers) makes a PNG', p)

    page.click('[data-tab="table"]')
    run.check(len(page.query_selector_all('.xt td')) == 64, 'table view has an 8 x 8 grid')
    page.screenshot(path=run.shot('table'), full_page=True)

    page.click('[data-tab="list"]')
    p = save(page, '#saveImg', 'export-list.png')
    run.check(p and open(p, 'rb').read(8) == b'\x89PNG\r\n\x1a\n', 'Save as image (list) makes a PNG', p)

    page.click('#copyTxt')
    try:
        page.wait_for_function("() => /Copied|copy here/.test(document.querySelector('#toast').textContent)", timeout=5000)
    except Exception:  # noqa: BLE001 - the check below reports what was on screen
        pass
    run.check('Copied' in page.inner_text('#toast'), 'Copy as text', page.inner_text('#toast'))

    p = save(page, '#saveFile', 'tournament.json')
    data = json.loads(open(p, encoding='utf-8').read())
    run.check(len(data['items']) == 8 and len(data['results']) == 28, 'Save file holds all 8 entries and 28 results')

    page.click('[data-breaktie] >> nth=0')
    page.wait_for_selector('#tieDlg[open]', timeout=5000)
    names = page.eval_on_selector_all('#tiePick .nm', 'els => els.map(e => e.textContent)')
    page.screenshot(path=run.shot('tie-break'))
    page.click('#tiePick [data-tp] >> nth=2')
    page.click('#tiePick [data-tp] >> nth=0')
    page.wait_for_selector('#tieDlg[open]', state='detached', timeout=5000)
    rows = ranking(page)
    run.check(rows[2:5] == [['3', names[2]], ['4', names[0]], ['5', names[1]]],
              'Break the tie puts them in the clicked order', rows[2:5])
    return rows


def check_persisted(page, run, expected_rows):
    page.wait_for_selector('.res-head h2', timeout=30000)
    rows = ranking(page)
    run.check(rows == expected_rows, 'everything is still there after reopening, including the broken tie', rows)


def check_restart(page, run):
    # A popup reopened the instant after Cancel must stay open (the browser's late "closed" notice
    # from the first popup used to shut the new one).
    page.evaluate("() => { const q = s => document.querySelector(s);"
                  " q('#rerun').click(); q('#askCancel').click(); q('#rerun').click(); }")
    page.wait_for_timeout(300)
    run.check(page.evaluate("document.querySelector('#askDlg').open"), 'a popup reopened right after Cancel stays open')
    page.click('#askCancel')
    page.wait_for_selector('#askDlg[open]', state='detached', timeout=5000)
    page.click('#rerun')
    page.wait_for_selector('#askDlg[open]', timeout=5000)
    page.keyboard.press('Escape')
    page.wait_for_selector('#askDlg[open]', state='detached', timeout=5000)
    run.check(page.inner_text('.res-head h2') == 'Final ranking', 'Escape closes the popup and keeps every pick')
    page.click('#rerun')
    page.wait_for_selector('#askDlg[open]', timeout=5000)
    run.check(page.inner_text('#askOk') == 'Restart', "Restart asks first, in the app's own popup", page.inner_text('#askMsg'))
    page.screenshot(path=run.shot('restart-popup'))
    page.click('#askOk')
    page.wait_for_selector('.fighter', timeout=10000)
    run.check(page.inner_text('.progress-txt b') == '1 of 28', 'Restart clears the picks', page.inner_text('.progress-txt b'))
    page.click('#toSetup')
    page.wait_for_selector('.tile', timeout=5000)
    run.check(len(page.query_selector_all('.tile')) == 8, 'Restart keeps all 8 entries')


NATO = ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel']


def _play_by_preference(page, order):
    """Plays every matchup, always picking whichever entry comes first in `order`."""
    n = 0
    while page.query_selector('.fighter'):
        a = page.get_attribute('.fighter[data-side="a"]', 'aria-label')[5:]
        b = page.get_attribute('.fighter[data-side="b"]', 'aria-label')[5:]
        before = page.inner_text('.progress-txt b')
        page.keyboard.press('ArrowLeft' if order.index(a) < order.index(b) else 'ArrowRight')
        _wait_progress_change(page, before)
        n += 1
        if n > 60:
            break
    return n


def _pick_format(page, f):
    """The other styles hide behind a small link until opened."""
    if not page.query_selector('.fmt-grid'):
        page.click('#moreFmts')
    page.click(f'[data-format="{f}"]')


def _restart(page):
    page.click('#rerun')
    page.wait_for_selector('#askDlg[open]', timeout=5000)
    page.click('#askOk')
    page.wait_for_timeout(300)


def check_formats(page, run):
    """Swiss (then finished as a round robin), single elimination, and double elimination."""
    page.click('#newT')
    if page.query_selector('#askDlg[open]'):
        page.click('#askOk')
    page.wait_for_selector('#lines')
    page.fill('#lines', '\n'.join(NATO))
    page.click('#addLines')
    run.check(not page.query_selector('.fmt-grid') and page.is_visible('#moreFmts') and '28 matchups' in page.inner_text('.dock p'),
              'a new tournament is a plain round robin, with other styles behind a small link')
    page.screenshot(path=run.shot('simple-start'), full_page=True)
    page.click('#moreFmts')
    page.wait_for_selector('.fmt-grid')
    counts = {f: page.inner_text(f'[data-format="{f}"] .fmt-count') for f in ('rr', 'rrplus', 'sort', 'swiss', 'topn', 'single', 'double')}
    run.check('28 matchups' in counts['rr'] and 'about 35 matchups' in counts['rrplus'] and 'about 23 matchups' in counts['sort'] and '20 matchups' in counts['swiss']
              and 'about 25 matchups' in counts['topn'] and '8 matchups' in counts['single']
              and '14 or 15 matchups' in counts['double'], 'each format shows its matchup count and time', counts)

    # Swiss, 4 rounds
    _pick_format(page, 'swiss')
    page.click('[data-rounds="-1"]')
    run.check('Swiss: 16 matchups' in page.inner_text('.dock p'), 'Swiss with 4 rounds is 16 matchups', page.inner_text('.dock p'))
    page.click('#dockGo')
    page.wait_for_selector('.fighter')
    run.check(page.inner_text('.progress-txt span') == 'Round 1 of 4', 'Swiss shows the round', page.inner_text('.progress-txt span'))
    page.screenshot(path=run.shot('swiss-matchup'))
    played = _play_by_preference(page, NATO)
    run.check(played == 16, 'Swiss plays 16 matchups', played)
    page.wait_for_selector('#toRR')
    rows = ranking(page)
    run.check(rows[0] == ['1', 'Alpha'], 'Swiss puts the best entry first', rows[:2])
    run.check('Swiss, 4 rounds' in page.inner_text('.fmt-line'), 'results say it was a 4-round Swiss')
    page.screenshot(path=run.shot('swiss-results'), full_page=True)

    # ...then finish it as a full round robin, keeping every pick
    page.click('#toRR')
    page.wait_for_selector('.fighter')
    run.check(page.inner_text('.progress-txt b') == '17 of 28', 'finishing as a round robin keeps all 16 picks', page.inner_text('.progress-txt b'))
    played = _play_by_preference(page, NATO)
    rows = ranking(page)
    run.check(played == 12 and rows == [[str(i + 1), x] for i, x in enumerate(NATO)],
              'the full round robin then ranks all 8 exactly right', rows)

    # Single elimination
    _restart(page)
    page.click('#toSetup')
    _pick_format(page, 'single')
    page.click('#dockGo')
    page.wait_for_selector('.fighter')
    run.check(not page.query_selector('#tieBtn'), 'no Tie button in a bracket')
    page.keyboard.press('ArrowDown')
    page.wait_for_selector('#toast:not([hidden])', timeout=3000)
    run.check('No ties' in page.inner_text('#toast'), 'the tie key explains there are no ties in a bracket', page.inner_text('#toast'))
    played = _play_by_preference(page, NATO)
    page.wait_for_selector('.res-head h2')
    rows = ranking(page)
    run.check(played == 8 and page.inner_text('.res-head h2') == 'Final results', 'single elimination: 7 matches plus the 3rd-place match', played)
    run.check(rows[0] == ['1', 'Alpha'] and 'Champion' in page.inner_text('.row >> nth=0'), 'the best entry is champion')
    page.screenshot(path=run.shot('single-results'), full_page=True)
    page.click('[data-tab="bracket"]')
    run.check(len(page.query_selector_all('.bm')) == 8 and 'Alpha' in page.inner_text('.champ-line'), 'bracket picture shows all 8 matches and the champion')
    page.screenshot(path=run.shot('single-bracket'), full_page=True)

    # Double elimination
    _restart(page)
    page.click('#toSetup')
    _pick_format(page, 'double')
    page.click('#dockGo')
    page.wait_for_selector('.fighter')
    for _ in range(3):
        a = page.get_attribute('.fighter[data-side="a"]', 'aria-label')[5:]
        b = page.get_attribute('.fighter[data-side="b"]', 'aria-label')[5:]
        before = page.inner_text('.progress-txt b')
        page.keyboard.press('ArrowLeft' if NATO.index(a) < NATO.index(b) else 'ArrowRight')
        _wait_progress_change(page, before)
    page.click('#toSetup')
    run.check(page.query_selector('.locked') and not page.query_selector('.tile-x'), 'entries lock once a bracket starts')
    page.click('#dockGo')
    page.wait_for_selector('.fighter')
    played = 3 + _play_by_preference(page, NATO)
    page.click('[data-tab="list"]')
    rows = ranking(page)
    run.check(played == 14, 'double elimination: 14 matches when the favorite never loses', played)
    run.check(rows[:2] == [['1', 'Alpha'], ['2', 'Bravo']], 'double elimination gets 1st and 2nd exactly right', rows[:3])
    page.click('[data-tab="bracket"]')
    run.check(all(page.query_selector(f'.bsec h3:text("{t}")') for t in ('Winners bracket', 'Losers bracket', 'Finals')),
              'bracket picture shows winners, losers, and finals')
    page.screenshot(path=run.shot('double-bracket'), full_page=True)

    # The guide
    _restart(page)
    page.click('#toSetup')
    page.click('#guideBtn')
    page.wait_for_selector('#guideDlg[open]')
    txt = page.inner_text('#guideBody')
    run.check(txt.count('Good for:') == 7 and txt.count('Not so good for:') == 7 and 'about 35 matchups for your 8 entries' in txt,
              'the guide says what all seven styles are good and bad at')
    page.screenshot(path=run.shot('guide'))
    page.click('#guideClose')
    run.check(not page.query_selector('#guideDlg[open]'), 'the guide closes')

    # Round robin+: one second look gets a different answer, and the third look settles it
    _pick_format(page, 'rrplus')
    page.click('#dockGo')
    page.wait_for_selector('.fighter')
    played, flipped, first_look = 0, False, None
    while page.query_selector('.fighter') and played < 80:
        a = page.get_attribute('.fighter[data-side="a"]', 'aria-label')[5:]
        b = page.get_attribute('.fighter[data-side="b"]', 'aria-label')[5:]
        sub = page.inner_text('.progress-txt span')
        better = 'ArrowLeft' if NATO.index(a) < NATO.index(b) else 'ArrowRight'
        key = better
        if sub == 'Second look at a close call':
            if first_look is None:
                first_look = page.inner_text('.progress-txt b')
                page.screenshot(path=run.shot('second-look'))
            if not flipped:
                key, flipped = ('ArrowRight' if better == 'ArrowLeft' else 'ArrowLeft'), True
        before = page.inner_text('.progress-txt b')
        page.keyboard.press(key)
        _wait_progress_change(page, before)
        played += 1
    run.check(first_look == '29 of 35', 'second looks start right after the 28 round robin matchups', first_look)
    rows = ranking(page)
    run.check(played == 36 and rows == [[str(i + 1), x] for i, x in enumerate(NATO)],
              'Round robin+: 7 second looks plus one third look, and the ranking is exact', (played, rows[:3]))
    line = page.inner_text('.fmt-line')
    run.check('7 close calls double-checked' in line and 'third look backed your first answer' in line,
              'the results say one answer changed and the third look settled it', line)
    marks = page.query_selector_all('.sure')
    run.check(len(marks) == 1 and 'Close call: you picked Alpha over Bravo 2 of 3 times.' in marks[0].inner_text()
              and 'One spot is a close call' in page.inner_text('.sure-sum'),
              'a how-sure marker flags the pair you went back and forth on', [m.inner_text() for m in marks])
    page.screenshot(path=run.shot('rrplus-results'), full_page=True)

    # Sort: consistent picks give an exact ranking, and every pair of neighbors gets a second look
    _restart(page)
    page.click('#toSetup')
    _pick_format(page, 'sort')
    page.click('#dockGo')
    page.wait_for_selector('.fighter')
    run.check(not page.query_selector('#tieBtn') and page.inner_text('.progress-txt span').startswith('About '),
              'Sort: no Tie button, and the count is marked as an estimate', page.inner_text('.progress-txt span'))
    page.screenshot(path=run.shot('sort-matchup'))
    played, looks = 0, 0
    while page.query_selector('.fighter') and played < 80:
        if page.inner_text('.progress-txt span') == 'Second look at a close call':
            looks += 1
        a = page.get_attribute('.fighter[data-side="a"]', 'aria-label')[5:]
        b = page.get_attribute('.fighter[data-side="b"]', 'aria-label')[5:]
        before = page.inner_text('.progress-txt b')
        page.keyboard.press('ArrowLeft' if NATO.index(a) < NATO.index(b) else 'ArrowRight')
        _wait_progress_change(page, before)
        played += 1
    rows = ranking(page)
    run.check(rows == [[str(i + 1), x] for i, x in enumerate(NATO)] and looks == 7 and 7 + 11 <= played <= 7 + 17,
              'Sort ranks all 8 exactly, with 7 second looks and far fewer than 28 matchups', (played, looks, rows[:3]))
    run.check('Sort, 7 pairs of neighbors double-checked' in page.inner_text('.fmt-line') and 'this order is solid' in page.inner_text('.sure-sum')
              and not page.query_selector('.sure'), 'Sort results say every neighbor was confirmed, with no close calls', page.inner_text('.fmt-line'))
    page.click('[data-tab="tiers"]')
    run.check(page.inner_text('.tier >> nth=0').count('Alpha') == 1 and 'place in the ranking' in page.inner_text('.note'), 'Sort tiers come from place in the ranking')
    page.click('[data-tab="list"]')
    page.screenshot(path=run.shot('sort-results'), full_page=True)

    # Top N
    _restart(page)
    page.click('#toSetup')
    _pick_format(page, 'topn')
    run.check('Top 3: about 25 matchups' in page.inner_text('.dock p'), 'Top 3 of 8 is about 25 matchups', page.inner_text('.dock p'))
    page.click('#dockGo')
    page.wait_for_selector('.fighter')
    run.check(not page.query_selector('#tieBtn') and page.inner_text('.progress-txt span') == 'Round 1, 8 still in',
              'Top N: no Tie button, and it shows how many are still in', page.inner_text('.progress-txt span'))
    page.screenshot(path=run.shot('topn-matchup'))
    played = _play_by_preference(page, NATO)
    rows = ranking(page)
    run.check(played == 25 and rows[:4] == [[str(i + 1), x] for i, x in enumerate(NATO[:4])],
              'Top 3: the 4 finalists (top 3 plus a spare) are ranked exactly', (played, rows[:5]))
    run.check(page.inner_text('.row >> nth=0').count('Finalist') == 1 and 'Out in round' in page.inner_text('.row >> nth=4'),
              'finalists and the rest are labeled')
    run.check('Top 3, out after 4 losses' in page.inner_text('.fmt-line') and page.query_selector('#toRR'),
              'results name the format and offer to finish as a round robin', page.inner_text('.fmt-line'))
    page.screenshot(path=run.shot('topn-results'), full_page=True)

    _restart(page)
    page.click('#toSetup')
    _pick_format(page, 'rr')
    run.check(page.get_attribute('[data-format="rr"]', 'aria-checked') == 'true', 'back to round robin')
    page.click('#hideFmts')
    run.check(not page.query_selector('.fmt-grid') and page.is_visible('#moreFmts'), 'Hide tucks the other styles away again')
