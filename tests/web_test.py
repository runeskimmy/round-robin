"""Browser test: the downloadable single-file app (web/round-robin.html) in Chrome."""
import os

from playwright.sync_api import sync_playwright

import flow
from common import CARDS_FIT_JS, ROOT, main, make_test_images


def body(run):
    images = make_test_images(run.dir / 'images')
    url = (ROOT / 'web' / 'round-robin.html').as_uri()
    errors = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome')
        except Exception:  # noqa: BLE001
            browser = p.chromium.launch(executable_path=os.environ.get('CHROME_PATH', '/usr/bin/google-chrome'))
        ctx = browser.new_context(viewport={'width': 1280, 'height': 860}, accept_downloads=True)
        page = ctx.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('dialog', lambda d: d.accept())
        page.goto(url)

        def save(pg, selector, name):
            with pg.expect_download(timeout=20000) as d:
                pg.click(selector)
            path = run.dir / name
            d.value.save_as(path)
            return str(path)

        flow.add_entries(page, run, images)
        flow.play_all(page, run)
        rows = flow.check_results(page, run, save)
        page.reload()
        flow.check_persisted(page, run, rows)
        flow.check_restart(page, run)
        flow.check_formats(page, run)
        hand = flow.check_hand(page, run, save)
        page.reload()
        page.wait_for_selector('.hand')
        flow.check_hand_after_reopen(page, run, hand)

        phone = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        mp = phone.new_page()
        mp.on('pageerror', lambda e: errors.append(str(e)))
        mp.goto(url)
        mp.fill('#lines', 'Pizza\nTacos\nA really long entry that wraps across several lines on a phone\nSushi')
        mp.click('#addLines')
        mp.click('#dockGo')
        mp.wait_for_selector('.fighter')
        box = mp.query_selector('#tieBtn').bounding_box()
        run.check(box['y'] + box['height'] <= 844, 'phone size: Tie button fits on screen', box)
        mp.screenshot(path=run.shot('phone-matchup'))

        # Bracket style cards: nothing may stick out of a card at any width, from a tiny phone to a desktop.
        # Ask until sure is set to Everything, its widest label. (The + used to hang off the card on phones.)
        sw = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        sp = sw.new_page()
        sp.on('pageerror', lambda e: errors.append(str(e)))
        sp.goto(url)
        sp.fill('#lines', '\n'.join(f'Frame {i}' for i in range(1, 14)))
        sp.click('#addLines')
        sp.click('#moreFmts')
        for _ in range(8):
            if sp.is_disabled('[data-askgoal="1"]'):
                break
            sp.click('[data-askgoal="1"]')
        bad = {}
        for w in range(300, 1301, 10):
            sp.set_viewport_size({'width': w, 'height': 844})
            got = sp.evaluate(CARDS_FIT_JS)
            if got:
                bad[w] = got[:3]
        run.check(sp.inner_text('[data-format="ask"] .step-val >> nth=0') == 'Everything' and not bad,
                  'bracket style cards fit at every width from 300 to 1300 pixels', dict(list(bad.items())[:5]))
        sp.set_viewport_size({'width': 390, 'height': 844})
        run.check(sp.evaluate("getComputedStyle(document.querySelector('.fmt-grid')).gridTemplateColumns.split(' ').length") == 1,
                  'on a phone the bracket styles stack in one column')
        sp.locator('.formats').screenshot(path=run.shot('phone-formats'))
        sw.close()
        run.check(not errors, 'no script errors', errors)
        browser.close()


if __name__ == '__main__':
    main('web', body)
