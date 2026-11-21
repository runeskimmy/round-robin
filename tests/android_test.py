"""Android test: install the APK on an emulator and use it like a person would.

Native parts (photo picker, confirm popups, back button) are driven with real taps and key presses
through adb. The page's state is read through the WebView's remote-debugging connection (debug builds only).

Usage: python3 tests/android_test.py path/to/app-debug.apk
"""
import itertools
import json
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

import websocket

from common import main, make_test_images

PKG = 'app.roundrobin'
PORT = 9222


def adb(*args, check=True, text=True):
    r = subprocess.run(['adb', *args], capture_output=True, text=text, timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError(f'adb {" ".join(args)} failed: {r.stderr or r.stdout}')
    return r.stdout


def screenshot(run, name):
    data = subprocess.run(['adb', 'exec-out', 'screencap', '-p'], capture_output=True, timeout=60).stdout
    with open(run.shot(name), 'wb') as f:
        f.write(data)


def ui_nodes(run=None, save_as=None):
    adb('shell', 'uiautomator', 'dump', '/sdcard/ui.xml', check=False)
    xml = adb('shell', 'cat', '/sdcard/ui.xml')
    if run and save_as:
        (run.dir / save_as).write_text(xml, encoding='utf-8')
    try:
        root = ET.fromstring(xml[xml.index('<?xml'):] if '<?xml' in xml else xml)
    except Exception:  # noqa: BLE001
        return []
    return list(root.iter('node'))


def center(node):
    x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds')))
    return (x1 + x2) // 2, (y1 + y2) // 2


def tap(x, y):
    adb('shell', 'input', 'tap', str(x), str(y))


class CDP:
    def __init__(self, run):
        self.ws = None
        self.reconnect = None
        deadline = time.time() + 60
        last = None
        while time.time() < deadline:
            try:
                targets = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
                page = next(t for t in targets if t.get('type') == 'page' and 'appassets' in t.get('url', ''))
                self.ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=90, suppress_origin=True)
                break
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1)
        run.check(self.ws, 'connected to the app page for testing', last)
        self.ids = itertools.count(1)

    def send(self, method, **params):
        i = next(self.ids)
        self.ws.send(json.dumps({'id': i, 'method': method, 'params': params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == i:
                if 'error' in msg:
                    raise RuntimeError(msg['error'])
                return msg.get('result', {})

    def js(self, expr):
        try:
            r = self.send('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
        except websocket.WebSocketConnectionClosedException:
            if not self.reconnect:
                raise
            self.reconnect()
            r = self.send('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
        if 'exceptionDetails' in r:
            raise RuntimeError(r['exceptionDetails'])
        return r.get('result', {}).get('value')

    def wait(self, expr, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(expr):
                return True
            time.sleep(0.3)
        return False

    def close(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


def forward_to_app(run):
    pid = None
    for _ in range(60):
        pid = adb('shell', 'pidof', PKG, check=False).strip()
        if pid and f'webview_devtools_remote_{pid}' in adb('shell', 'cat', '/proc/net/unix', check=False):
            break
        time.sleep(1)
    adb('forward', '--remove-all', check=False)
    adb('forward', f'tcp:{PORT}', f'localabstract:webview_devtools_remote_{pid}')
    return pid


def start_app(run):
    adb('shell', 'am', 'start', '-W', '-n', f'{PKG}/.MainActivity')
    pid = None
    for _ in range(60):
        pid = adb('shell', 'pidof', PKG, check=False).strip()
        sockets = adb('shell', 'cat', '/proc/net/unix', check=False)
        if pid and f'webview_devtools_remote_{pid}' in sockets:
            break
        time.sleep(1)
    run.check(pid, 'app starts', pid)
    adb('forward', '--remove-all', check=False)
    adb('forward', f'tcp:{PORT}', f'localabstract:webview_devtools_remote_{pid}')
    cdp = CDP(run)
    run.check(cdp.wait("!!document.querySelector('header .brand')", 30), 'app page loads from inside the APK')

    def reconnect():
        old = pid
        run.log('!! lost the connection to the app page; app process before:', old,
                'now:', adb('shell', 'pidof', PKG, check=False).strip() or 'not running')
        new = forward_to_app(run)
        run.log('!! reconnecting to process', new, '(same process)' if new == old else '(APP RESTARTED)')
        fresh = CDP(run)
        cdp.ws = fresh.ws
    cdp.reconnect = reconnect
    return cdp


def tap_element(cdp, selector):
    """Real tap on a page element (gives the page a genuine user gesture)."""
    find = "document.querySelector('" + selector + "')"
    for _ in range(3):
        rect = cdp.js("(() => { const r = " + find + ".getBoundingClientRect();"
                      " return [r.left + r.width / 2, r.top + Math.min(r.height / 2, 60), window.devicePixelRatio, window.innerHeight]; })()")
        if 0 < rect[1] < rect[3] - 20:
            break
        print(f'{selector} is off screen (y={rect[1]:.0f} of {rect[3]}), scrolling to it', flush=True)
        cdp.js("document.activeElement && document.activeElement.blur(); " + find + ".scrollIntoView({ block: 'center', behavior: 'instant' })")
        time.sleep(1)
    web = next(n for n in ui_nodes() if n.get('class') == 'android.webkit.WebView')
    x1, y1 = map(int, re.findall(r'\d+', web.get('bounds'))[:2])
    x, y = int(x1 + rect[0] * rect[2]), int(y1 + rect[1] * rect[2])
    print(f'tap {selector} at {x},{y}', flush=True)
    tap(x, y)


def toast(cdp):
    return cdp.js("document.querySelector('#toast').hidden ? '' : document.querySelector('#toast').textContent")


def body(run):
    adb('logcat', '-c', check=False)
    try:
        steps(run)
    finally:
        try:
            screenshot(run, 'last-screen')
            log = adb('logcat', '-d', '-v', 'time', check=False)
            keep = [l for l in log.splitlines() if re.search(
                r'roundrobin|AndroidRuntime|FATAL|chromium|cr_|WebView|ActivityManager|ActivityTaskManager|lowmemory|PhotoPicker|ContentResolver', l)]
            (run.dir / 'logcat.txt').write_text('\n'.join(keep[-4000:]), encoding='utf-8')
        except Exception as e:  # noqa: BLE001
            run.log('could not save logcat:', e)


def steps(run):
    apk = sys.argv[1]
    images = make_test_images(run.dir / 'images')
    run.log(adb('shell', 'getprop', 'ro.build.version.release').strip(), '(Android version)')

    adb('install', '-r', apk)
    run.check(PKG in adb('shell', 'pm', 'list', 'packages', PKG), 'APK installs')
    adb('shell', 'mkdir', '-p', '/sdcard/Pictures')
    for img in images:
        name = img.replace('\\', '/').split('/')[-1]
        adb('push', img, f'/sdcard/Pictures/{name}')
    adb('shell', 'content', 'call', '--uri', 'content://media', '--method', 'scan_volume', '--arg', 'external_primary', check=False)
    for img in images:
        name = img.replace('\\', '/').split('/')[-1]
        adb('shell', 'am', 'broadcast', '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
            '-d', f'file:///sdcard/Pictures/{name.replace(" ", "%20")}', check=False)
    time.sleep(3)

    cdp = start_app(run)
    time.sleep(3)
    screenshot(run, 'opened')
    run.log('page size:', cdp.js("[innerWidth, innerHeight, devicePixelRatio, getComputedStyle(document.body).backgroundColor]"))
    cdp.js("document.querySelector('#lines').value = 'Pizza\\nTacos\\nRamen\\nSushi\\nBurgers';"
           "document.querySelector('#addLines').click()")
    run.check(cdp.wait("document.querySelectorAll('.tile').length === 5"), 'typed entries added')

    # Photo picker: a real tap on the drop area, then pick 3 photos and tap Add.
    tap_element(cdp, '#dropBtn')
    time.sleep(4)
    screenshot(run, 'photo-picker')
    nodes = ui_nodes(run, 'ui-photo-picker.xml')
    pkgs = sorted({n.get('package') for n in nodes})
    run.log('screen apps:', pkgs)
    run.check(any('media' in p or 'photopicker' in p or 'documentsui' in p for p in pkgs), 'tapping the drop area opens the photo picker', pkgs)
    photos = [n for n in nodes
              if re.search(r'photo|image', n.get('content-desc', ''), re.I)
              and (n.get('clickable') == 'true' or n.get('long-clickable') == 'true'
                   or n.get('content-desc', '').startswith('Photo taken'))]
    run.log('photo items found:', len(photos), [p.get('content-desc') for p in photos[:5]])
    for node in photos[:3]:
        tap(*center(node))
        time.sleep(0.8)
    screenshot(run, 'photos-selected')
    nodes = ui_nodes(run, 'ui-photo-picker-selected.xml')
    add = next((n for n in nodes if re.match(r'^(Add|Done|Select)', n.get('text', '')) and n.get('enabled') == 'true'), None)
    run.check(add is not None, 'picker shows an Add button after selecting', [n.get('text') for n in nodes if n.get('text')][:20])
    tap(*center(add))
    time.sleep(2)
    screenshot(run, 'after-add')
    came_back = cdp.wait("document.querySelectorAll('.tile').length === 8", 20)
    run.log('photo read errors:', cdp.js("JSON.stringify(window.__rrAddErrors || [])"))
    run.check(came_back, 'three photos come back into the app', cdp.js("document.querySelectorAll('.tile').length"))
    run.check(cdp.js("[...document.querySelectorAll('.tile-face img')].every(i => i.naturalWidth > 0)"), 'the photos display')
    run.log('photo names:', cdp.js("[...document.querySelectorAll('.tile-name')].map(e => e.value)"))
    screenshot(run, 'entries')

    # Play all 28 matchups (left card every time; the ranking math is covered by the other tests).
    cdp.js("document.querySelector('#dockGo').click()")
    run.check(cdp.wait("!!document.querySelector('.fighter')"), 'matchups start')
    screenshot(run, 'matchup')
    done = cdp.js("""(async () => {
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      let n = 0;
      while (document.querySelector('.fighter') && n < 40) {
        const before = document.querySelector('.progress-txt b').textContent;
        document.querySelector('.fighter[data-side="a"]').click();
        for (let i = 0; i < 100; i++) {
          const el = document.querySelector('.progress-txt b');
          if (!el || el.textContent !== before) break;
          await sleep(20);
        }
        n++;
      }
      return n;
    })()""")
    run.check(done == 28 and cdp.wait("document.body.dataset.view === 'results'"), 'played all 28 matchups', done)
    screenshot(run, 'ranking')

    cdp.js("document.querySelector('#saveImg').click()")
    cdp.wait("/Saved|Couldn't/.test(document.querySelector('#toast').textContent)", 20)
    msg = toast(cdp)
    run.check('Pictures/Round Robin' in msg, 'Save as image says it went to Pictures/Round Robin', msg)
    run.check('.png' in adb('shell', "ls '/sdcard/Pictures/Round Robin'", check=False), 'the PNG is really in Pictures/Round Robin')
    screenshot(run, 'saved-image')

    cdp.js("document.querySelector('#saveFile').click()")
    cdp.wait("/\\.json to your|Couldn't save the file/.test(document.querySelector('#toast').textContent)", 20)
    msg = toast(cdp)
    run.check('Download/Round Robin' in msg, 'Save file says it went to Download/Round Robin', msg)
    run.check('.json' in adb('shell', "ls '/sdcard/Download/Round Robin'", check=False), 'the save file is really in Download/Round Robin')

    cdp.js("document.querySelector('#copyTxt').click()")
    cdp.wait("/Copied|copy here/.test(document.querySelector('#toast').textContent)", 10)
    run.check('Copied' in toast(cdp), 'Copy as text', toast(cdp))
    time.sleep(10)  # Android's "copied" bubble sits on top of everything for a few seconds and swallows taps


    # Back button: first press goes to the entries screen, second press closes the app.
    adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
    run.check(cdp.wait("document.body.dataset.view === 'setup'", 10), 'back button returns to the entries screen')
    cdp.close()
    adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
    time.sleep(2)
    top = adb('shell', 'dumpsys', 'activity', 'activities', check=False)
    resumed = [l for l in top.splitlines() if 'ResumedActivity' in l]
    run.check(not any(PKG in l for l in resumed), 'back again closes the app', resumed[:2])

    # Reopen: everything should still be there.
    cdp = start_app(run)
    time.sleep(4)  # let the emulator finish drawing the reopened app before tapping
    run.check(cdp.wait("document.querySelectorAll('.tile').length === 8", 15), 'entries are still there after reopening')
    dock = cdp.js("document.querySelector('.dock p') ? document.querySelector('.dock p').innerText : ''")
    run.check('28 of 28' in dock, 'all 28 picks are still there after reopening', dock)

    # Restart asks first in the app's own popup. Cancel should do nothing; Restart should clear the picks
    # (from the entries screen it stays on the entries screen).
    cdp.js("document.querySelector('#rerun').click()")
    run.check(cdp.wait("document.querySelector('#askDlg').open"), "Restart asks first, in the app's own popup")
    time.sleep(1)
    screenshot(run, 'restart-popup')
    tap_element(cdp, '#askCancel')
    run.check(cdp.wait("!document.querySelector('#askDlg').open && /28 of 28/.test(document.querySelector('.dock p').innerText)", 10),
              'tapping Cancel keeps every pick')
    cdp.js("document.querySelector('#rerun').click()")
    cdp.wait("document.querySelector('#askDlg').open")
    time.sleep(1)
    run.log('popup open 1s after reopening:', cdp.js("document.querySelector('#askDlg').open"))
    tap_element(cdp, '#askOk')
    cleared = "/28 matchups<\\/b> for 8 entries/.test(document.querySelector('.dock p').innerHTML)"
    if not cdp.wait(cleared, 6):
        screenshot(run, 'restart-tap-missed')
        run.log('first tap on Restart did not register; dialog open:', cdp.js("document.querySelector('#askDlg').open"))
        if not cdp.js("document.querySelector('#askDlg').open"):
            cdp.js("document.querySelector('#rerun').click()")
            cdp.wait("document.querySelector('#askDlg').open")
            time.sleep(1)
        tap_element(cdp, '#askOk')
    run.check(cdp.wait("/28 matchups<\\/b> for 8 entries/.test(document.querySelector('.dock p').innerHTML)", 10),
              'tapping Restart clears the picks and keeps the entries',
              cdp.js("document.querySelector('.dock p').innerText"))
    screenshot(run, 'restarted')

    # Open the popup, tap Cancel for real, reopen, and make sure it stays open. 4 rounds.
    cdp.js("document.querySelector('#lines').value = ''")
    spurious = []
    for i in range(4):
        cdp.js("setTimeout(() => document.querySelector('#newT').click(), 0); true")
        if not cdp.wait("document.querySelector('#askDlg').open", 5):
            spurious.append((i, 'did not open'))
            continue
        time.sleep(1.5)
        if not cdp.js("document.querySelector('#askDlg').open"):
            spurious.append(i)
            screenshot(run, f'popup-closed-itself-{i}')
            continue
        tap_element(cdp, '#askCancel')
        cdp.wait("!document.querySelector('#askDlg').open", 5)
        time.sleep(0.3)
    for s_ in spurious:
        run.log('popup closed by itself:', s_)
    run.check(not spurious, 'popup never closes by itself (4 rounds of open, Cancel, reopen)', len(spurious))
    run.check(cdp.js("document.querySelectorAll('.tile').length") == 8, 'Cancel on New tournament keeps everything')

    # Brackets on the phone: pick a format with a real tap, then a quick double elimination.
    cdp.js("document.querySelector('#newT').click()")
    cdp.wait("document.querySelector('#askDlg').open", 5)
    cdp.js("document.querySelector('#askOk').click()")
    cdp.wait("!!document.querySelector('#lines')", 5)
    cdp.js("document.querySelector('#lines').value = 'Alpha\\nBravo\\nCharlie\\nDelta\\nEcho\\nFoxtrot'; document.querySelector('#addLines').click()")
    cdp.js("document.activeElement && document.activeElement.blur()")
    time.sleep(1)
    run.check(cdp.js("!document.querySelector('.fmt-grid') && !!document.querySelector('#moreFmts')"),
              'a new tournament is a plain round robin, with other styles behind a small link')
    screenshot(run, 'simple-start')
    tap_element(cdp, '#moreFmts')
    run.check(cdp.wait("!!document.querySelector('.fmt-grid')", 5), 'tapping "Other bracket styles" shows them')
    time.sleep(1)
    tap_element(cdp, '[data-format="double"]')
    run.check(cdp.wait("document.querySelector('[data-format=\\'double\\']').getAttribute('aria-checked') === 'true'", 5), 'tapping a format card picks it')
    screenshot(run, 'format-picker')
    cdp.js("document.querySelector('#dockGo').click()")
    run.check(cdp.wait("!!document.querySelector('.fighter') && !document.querySelector('#tieBtn')"), 'bracket matchups start, with no Tie button')
    screenshot(run, 'double-matchup')
    picks = cdp.js("""(() => { const L = id => window.__rr.state().items.find(i => i.id === id).label; let n = 0;
      while (window.__rr.current() && n < 30) { const m = window.__rr.current(); window.__rr.pick(L(m.a) < L(m.b) ? 'a' : 'b'); n++; }
      return n; })()""")
    run.check(picks == 10, 'double elimination with 6 entries: 10 matches', picks)
    cdp.js("document.querySelector('[data-tab=\\'bracket\\']').click()")
    run.check(cdp.wait("!!document.querySelector('.champ-line') && document.querySelectorAll('.bm').length >= 10"), 'the bracket picture shows on the phone')
    run.check('Alpha' in cdp.js("document.querySelector('.champ-line').innerText"), 'the best entry is champion')
    screenshot(run, 'double-bracket')

    # The guide and Top N on the phone, with real taps
    cdp.js("document.querySelector('#rerun').click()")
    cdp.wait("document.querySelector('#askDlg').open", 5)
    cdp.js("document.querySelector('#askOk').click()")
    time.sleep(0.5)
    cdp.js("document.querySelector('#toSetup').click()")
    cdp.wait("!!document.querySelector('#guideBtn')", 5)
    cdp.js("document.activeElement && document.activeElement.blur()")
    time.sleep(0.5)
    tap_element(cdp, '#guideBtn')
    run.check(cdp.wait("document.querySelector('#guideDlg').open", 5), 'tapping "Which one should I pick?" opens the guide')
    run.check(cdp.js("document.querySelector('#guideBody').innerText.split('Good for:').length - 1") == 6, 'the guide covers all six formats')
    screenshot(run, 'guide')
    cdp.js("document.querySelector('#guideClose').click()")
    time.sleep(0.5)
    tap_element(cdp, '[data-format="topn"]')
    run.check(cdp.wait("document.querySelector('[data-format=\\'topn\\']').getAttribute('aria-checked') === 'true'", 5), 'tapping the Top N card picks it')
    cdp.js("document.querySelector('#dockGo').click()")
    run.check(cdp.wait("!!document.querySelector('.fighter') && !document.querySelector('#tieBtn')"), 'Top N matchups start, with no Tie button')
    picks = cdp.js("""(() => { const L = id => window.__rr.state().items.find(i => i.id === id).label; let n = 0;
      while (window.__rr.current() && n < 60) { const m = window.__rr.current(); window.__rr.pick(L(m.a) < L(m.b) ? 'a' : 'b'); n++; }
      return n; })()""")
    top4 = cdp.js("window.__rr.ranking().slice(0, 4).map(r => window.__rr.state().items.find(i => i.id === r.id).label).join(',')")
    run.check(picks == 17 and top4 == 'Alpha,Bravo,Charlie,Delta', 'Top 3 of 6: 14 matchups plus 3 second looks, finalists ranked exactly', (picks, top4))
    screenshot(run, 'topn-results')

    cdp.close()


if __name__ == '__main__':
    main('android', body)
