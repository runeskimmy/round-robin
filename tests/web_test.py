"""Browser test: the downloadable single-file app (web/round-robin.html) in Chrome."""
import os

from playwright.sync_api import sync_playwright

import flow
from common import ROOT, main, make_test_images


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
        run.check(not errors, 'no script errors', errors)
        browser.close()


if __name__ == '__main__':
    main('web', body)
