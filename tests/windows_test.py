"""Windows test: install with the real installer, then drive the real app window.

The app is started with its test hook (ROUNDROBIN_TEST_DEBUG_PORT) switched on, so Playwright can
operate the page inside the app's own window (not a separate browser).

Usage: python tests/windows_test.py path\\to\\RoundRobin-Setup.exe
"""
import ctypes
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

import flow
from common import main, make_test_images

LOCAL = pathlib.Path(os.environ['LOCALAPPDATA'])
INSTALL_DIR = LOCAL / 'Programs' / 'Round Robin'
DATA_DIR = LOCAL / 'RoundRobin'
APPDATA = pathlib.Path(os.environ['APPDATA'])
DESKTOP = pathlib.Path(os.environ['USERPROFILE']) / 'Desktop'
DOWNLOADS = pathlib.Path(os.environ['USERPROFILE']) / 'Downloads'
PORT = 9222
user32 = ctypes.windll.user32


def desktop_shot(run, name):
    try:
        from PIL import ImageGrab
        ImageGrab.grab(all_screens=True).save(run.shot(name))
    except Exception as e:  # noqa: BLE001
        run.log('desktop screenshot failed:', e)


def find_window():
    return user32.FindWindowW(None, 'Round Robin')


def port_open(port):
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=2)
        return True
    except Exception:  # noqa: BLE001
        return False


def launch(run, port):
    run.check(not port_open(port), f'port {port} is free before launching')
    env = dict(os.environ, ROUNDROBIN_TEST_DEBUG_PORT=str(port))
    proc = subprocess.Popen([str(INSTALL_DIR / 'RoundRobin.exe')], env=env)
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            run.check(False, 'app keeps running after launch', f'exited with code {proc.returncode}')
        try:
            info = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=2))
            run.log('WebView2:', info.get('Browser'))
            break
        except Exception:  # noqa: BLE001
            time.sleep(1)
    else:
        desktop_shot(run, 'launch-timeout')
        run.check(False, 'app window opens and its page starts', 'no debugging port after 90s')
    for _ in range(30):
        if find_window():
            break
        time.sleep(0.5)
    run.check(find_window(), 'a window titled "Round Robin" is open')
    return proc


def connect(p, run, port):
    browser = p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
    for _ in range(60):
        pages = [pg for c in browser.contexts for pg in c.pages if pg.url.startswith('https://rr.localhost')]
        if pages:
            page = pages[0]
            page.on('dialog', lambda d: d.accept())
            return browser, page
        time.sleep(0.5)
    run.check(False, 'app page loads from its built-in address', [pg.url for c in browser.contexts for pg in c.pages])


def close_app(proc, run):
    hwnd = find_window()
    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE, same as clicking the X
    try:
        proc.wait(timeout=20)
        run.check(True, 'closing the window quits the app')
    except subprocess.TimeoutExpired:
        proc.kill()
        run.check(False, 'closing the window quits the app')
    # Edge's engine shuts down a moment after the window; wait so the next launch starts clean.
    for _ in range(30):
        if not subprocess.run('tasklist /FI "IMAGENAME eq msedgewebview2.exe" | find /I "msedgewebview2"',
                              shell=True, capture_output=True).stdout:
            break
        time.sleep(1)


def body(run):
    installer = pathlib.Path(sys.argv[1]).resolve()
    images = make_test_images(run.dir / 'images')

    subprocess.run([str(installer), '/S'], check=True, timeout=120)
    time.sleep(2)
    run.check((INSTALL_DIR / 'RoundRobin.exe').exists(), 'installer puts the app in your user folder', INSTALL_DIR)
    run.check((APPDATA / 'Microsoft/Windows/Start Menu/Programs/Round Robin.lnk').exists(), 'Start menu shortcut')
    run.check((DESKTOP / 'Round Robin.lnk').exists(), 'desktop shortcut')
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Uninstall\RoundRobin') as k:
        run.check(winreg.QueryValueEx(k, 'DisplayName')[0] == 'Round Robin', 'listed in Settings > Apps for uninstalling')

    proc = launch(run, PORT)
    time.sleep(2)
    desktop_shot(run, 'desktop-app-open')
    with sync_playwright() as p:
        browser, page = connect(p, run, PORT)
        run.check(page.url.startswith('https://rr.localhost'), 'page loads from the app, not the internet', page.url)

        def save(pg, selector, name):
            try:
                with pg.expect_download(timeout=20000) as d:
                    pg.click(selector)
                path = run.dir / name
                d.value.save_as(path)
                return str(path)
            except Exception as e:  # noqa: BLE001 - fall back to Windows' own Downloads folder
                run.log('download event not seen, checking Downloads folder:', e)
                time.sleep(3)
                found = sorted(DOWNLOADS.glob('round-robin*'), key=lambda f: f.stat().st_mtime)
                return str(found[-1]) if found else None

        flow.add_entries(page, run, images)
        flow.play_all(page, run)
        desktop_shot(run, 'desktop-ranking')
        rows = flow.check_results(page, run, save)
        browser.close()
    close_app(proc, run)
    run.check(DATA_DIR.exists() and any(DATA_DIR.iterdir()), 'your data is kept in AppData\\Local\\RoundRobin', DATA_DIR)

    proc = launch(run, PORT + 1)
    with sync_playwright() as p:
        browser, page = connect(p, run, PORT + 1)
        flow.check_persisted(page, run, rows)
        desktop_shot(run, 'desktop-reopened')
        flow.check_restart(page, run)
        browser.close()
    close_app(proc, run)

    subprocess.run([str(INSTALL_DIR / 'Uninstall.exe'), '/S', f'_?={INSTALL_DIR}'], check=True, timeout=120)
    time.sleep(2)
    run.check(not (INSTALL_DIR / 'RoundRobin.exe').exists(), 'uninstalling removes the app')
    run.check(not (DESKTOP / 'Round Robin.lnk').exists(), 'uninstalling removes the shortcuts')
    run.check(DATA_DIR.exists(), 'uninstalling keeps your tournaments')


if __name__ == '__main__':
    main('windows', body)
