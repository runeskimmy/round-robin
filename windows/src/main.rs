// Round Robin for Windows: a native window that shows the app with Windows' built-in Edge engine (WebView2).
#![windows_subsystem = "windows"]

use std::borrow::Cow;
use std::path::PathBuf;
use tao::{
    dpi::LogicalSize,
    event::{Event, WindowEvent},
    event_loop::{ControlFlow, EventLoop},
    window::{Icon, WindowBuilder},
};
use wry::{
    http::{header::CONTENT_TYPE, Response},
    WebContext, WebViewBuilder, WebViewBuilderExtWindows,
};

const HTML: &[u8] = include_bytes!("../../web/round-robin.html");
const ICON_RGBA: &[u8] = include_bytes!("../icon-64.rgba");

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
    let built = WebViewBuilder::new_with_web_context(&mut context)
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

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;
        let _keep_alive = &webview;
        if let Event::WindowEvent { event: WindowEvent::CloseRequested, .. } = event {
            *control_flow = ControlFlow::Exit;
        }
    });
}
