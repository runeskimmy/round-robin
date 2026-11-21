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
    page.click('#rerun')  # confirm() is accepted by the caller's dialog handler
    page.wait_for_selector('.fighter', timeout=10000)
    run.check(page.inner_text('.progress-txt b') == '1 of 28', 'Restart clears the picks', page.inner_text('.progress-txt b'))
    page.click('#toSetup')
    page.wait_for_selector('.tile', timeout=5000)
    run.check(len(page.query_selector_all('.tile')) == 8, 'Restart keeps all 8 entries')
