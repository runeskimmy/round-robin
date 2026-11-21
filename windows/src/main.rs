// Round Robin for Windows: a native window that shows the app with Windows' built-in Edge engine (WebView2).
#![windows_subsystem = "windows"]

use std::borrow::Cow;
use std::path::PathBuf;
use std::rc::Rc;
use std::cell::Cell;
use std::time::{Duration, Instant};
use tao::{
    dpi::LogicalSize,
    event::{Event, StartCause, WindowEvent},
    event_loop::{ControlFlow, EventLoop},
    window::{Icon, WindowBuilder},
};
use wry::{
    http::{header::CONTENT_TYPE, Response},
    PageLoadEvent, WebContext, WebViewBuilder, WebViewBuilderExtWindows,
};

const HTML: &[u8] = include_bytes!("../../web/round-robin.html");
const ICON_RGBA: &[u8] = include_bytes!("../icon-64.rgba");
// Where Windows serves the built-in page (wry maps rr://localhost/ to this address).
const APP_URL: &str = "https://rr.localhost/";
// If the page hasn't finished loading by then, ask for it again (Edge's engine occasionally drops
// the very first request on a cold start, which leaves an empty white window).
const LOAD_CHECK: Duration = Duration::from_secs(4);
const MAX_RETRIES: u32 = 5;

#[link(name = "user32")]
unsafe extern "system" {
    fn MessageBoxW(hwnd: isize, text: *const u16, caption: *const u16, utype: u32) -> i32;
}

fn message(text: &str) {
    let w = |s: &str| s.encode_utf16().chain(std::iter::once(0)).collect::<Vec<u16>>();
    unsafe { MessageBoxW(0, w(text).as_ptr(), w("Round Robin").as_ptr(), 0x10) };
}

fn data_dir() -> Option<PathBuf> {
    // Your tournaments live here, so they survive app updates: %LOCALAPPDATA%\RoundRobin
    let dir = PathBuf::from(std::env::var_os("LOCALAPPDATA")?).join("RoundRobin");
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir)
}

fn main() {
    let event_loop = EventLoop::new();
    let window = match WindowBuilder::new()
        .with_title("Round Robin")
        .with_inner_size(LogicalSize::new(1200.0, 860.0))
        .with_min_inner_size(LogicalSize::new(380.0, 520.0))
        .with_window_icon(Icon::from_rgba(ICON_RGBA.to_vec(), 64, 64).ok())
        .build(&event_loop)
    {
        Ok(w) => w,
        Err(e) => { message(&format!("Round Robin couldn't open a window.\n\n{e}")); return; }
    };

    let mut context = WebContext::new(data_dir());
    let mut builder = WebViewBuilder::new_with_web_context(&mut context);
    // Test hook, off unless this variable is set: lets automated tests drive the page.
    if let Some(port) = std::env::var("ROUNDROBIN_TEST_DEBUG_PORT").ok().and_then(|p| p.parse::<u16>().ok()) {
        builder = builder.with_additional_browser_args(format!(
            "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection --remote-debugging-port={port}"
        ));
    }
    let loaded = Rc::new(Cell::new(false));
    let loaded_flag = loaded.clone();
    let built = builder
        .with_on_page_load_handler(move |event, url| {
            if matches!(event, PageLoadEvent::Finished) && (url.starts_with(APP_URL) || url.starts_with("rr://")) {
                loaded_flag.set(true);
            }
        })
        .with_https_scheme(true)
        .with_custom_protocol("rr".into(), |_id, _request| {
            Response::builder()
                .header(CONTENT_TYPE, "text/html; charset=utf-8")
                .body(Cow::Borrowed(HTML))
                .unwrap()
        })
        .with_url("rr://localhost/")
        .with_background_color((214, 236, 232, 255))
        .build(&window);

    let webview = match built {
        Ok(v) => v,
        Err(e) => {
            message(&format!(
                "Round Robin needs Microsoft Edge WebView2, which comes with Windows 10 and 11.\n\
                 If it's missing, install the \"Evergreen\" runtime from microsoft.com/edge/webview2 and try again.\n\nDetails: {e}"
            ));
            return;
        }
    };

    let mut next_check = Instant::now() + LOAD_CHECK;
    let mut retries = 0;
    event_loop.run(move |event, _, control_flow| {
        match event {
            Event::NewEvents(StartCause::ResumeTimeReached { .. }) if !loaded.get() => {
                retries += 1;
                let _ = webview.load_url(APP_URL);
                next_check = Instant::now() + LOAD_CHECK;
            }
            Event::WindowEvent { event: WindowEvent::CloseRequested, .. } => {
                *control_flow = ControlFlow::Exit;
                return;
            }
            _ => {}
        }
        *control_flow = if loaded.get() || retries >= MAX_RETRIES {
            ControlFlow::Wait
        } else {
            ControlFlow::WaitUntil(next_check)
        };
    });
}
