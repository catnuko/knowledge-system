//! knowledge-engine 桌面端壳。
//!
//! 启动流程：
//!   1. 探测 127.0.0.1:KE_PORT（默认 8000）是否已有后端在监听；
//!   2. 没有则按优先级拉起后端：
//!        环境变量 KE_BACKEND_CMD（可执行文件路径）
//!        > 随包分发的单文件后端（resource_dir/knowledge-engine-backend，PyInstaller 产物）
//!        > 开发模式 `ke serve --port <KE_PORT>`（pip install -e . 后可用，host 固定 127.0.0.1）
//!   3. 轮询等待后端就绪（最长约 60s）；
//!   4. 主窗口跳转到 http://127.0.0.1:<KE_PORT>（与后端同源，面板零改动复用）。
//!
//! 退出时自动结束由本进程拉起的后端子进程。

use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

/// 剪贴板文本采集快捷键（跨平台：Cmd+Shift+C 在 mac，Ctrl+Shift+C 在其他）
fn capture_shortcut() -> Shortcut {
    let modifier = if cfg!(target_os = "macos") {
        Modifiers::SUPER | Modifiers::SHIFT
    } else {
        Modifiers::CONTROL | Modifiers::SHIFT
    };
    Shortcut::new(Some(modifier), Code::KeyC)
}

/// 把剪贴板文本 POST 到本地后端 /api/ingest。
/// 用 std::net::TcpStream 手写最小 HTTP，避免引入 reqwest 重依赖。
fn post_clipboard_to_backend(port: u16, text: &str) {
    let body = format!(
        "{{\"text\":{},\"kind\":\"clipboard\"}}",
        serde_json::Value::String(text.to_string())
    );
    let req = format!(
        "POST /api/ingest HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\
         Content-Type: application/json\r\nContent-Length: {len}\r\n\r\n{body}",
        len = body.len(),
    );
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    if let Ok(mut stream) = TcpStream::connect_timeout(&addr, CONNECT_TIMEOUT) {
        use std::io::{Read, Write};
        let _ = stream.set_write_timeout(Some(CONNECT_TIMEOUT));
        if stream.write_all(req.as_bytes()).is_ok() {
            let _ = stream.read(&mut [0u8; 256]); // 丢弃响应
        }
    }
}

const DEFAULT_PORT: u16 = 8000;
const HEALTH_RETRIES: u32 = 120; // 120 × 500ms ≈ 60s
const HEALTH_INTERVAL: Duration = Duration::from_millis(500);
const CONNECT_TIMEOUT: Duration = Duration::from_millis(400);

/// 记录由桌面端拉起的后端子进程，退出时回收。
struct BackendState(Mutex<Option<Child>>);

fn backend_port() -> u16 {
    std::env::var("KE_PORT")
        .ok()
        .and_then(|v| v.trim().parse().ok())
        .filter(|p: &u16| *p > 0)
        .unwrap_or(DEFAULT_PORT)
}

fn backend_addr(port: u16) -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], port))
}

/// 后端是否已在监听。
fn is_up(port: u16) -> bool {
    TcpStream::connect_timeout(&backend_addr(port), CONNECT_TIMEOUT).is_ok()
}

/// 随包分发的后端可执行文件名（Windows 上 PyInstaller 产物带 .exe 后缀）
fn backend_binary_name() -> &'static str {
    if cfg!(windows) { "knowledge-engine-backend.exe" } else { "knowledge-engine-backend" }
}

/// 按优先级解析后端启动命令。
fn resolve_backend_command(app: &tauri::AppHandle) -> Option<(PathBuf, Vec<String>)> {
    // 1. 显式指定（可执行文件路径）
    if let Ok(cmd) = std::env::var("KE_BACKEND_CMD") {
        let cmd = cmd.trim();
        if !cmd.is_empty() {
            return Some((PathBuf::from(cmd), Vec::new()));
        }
    }
    // 2. 随包分发的 PyInstaller 单文件后端（资源目录布局因打包方式而异，逐个候选查找）
    if let Ok(dir) = app.path().resource_dir() {
        let name = backend_binary_name();
        let candidates = [
            dir.join(name),
            dir.join("resources").join(name),
            dir.join("_up_/backend-dist").join(name),
        ];
        if let Some(bundled) = candidates.into_iter().find(|p| p.is_file()) {
            return Some((bundled, Vec::new()));
        }
    }
    // 3. 开发模式：ke CLI（pip install -e . 后位于 PATH）。注意 ke serve 仅支持 --port，
    //    host 在实现中固定为 127.0.0.1
    Some((
        PathBuf::from("ke"),
        vec![
            "serve".into(),
            "--port".into(),
            backend_port().to_string(),
        ],
    ))
}

/// 拉起后端进程，标准输出/错误写入应用日志目录 backend.log。
fn spawn_backend(app: &tauri::AppHandle) -> std::io::Result<Child> {
    let (cmd, args) =
        resolve_backend_command(app).expect("无法定位后端启动命令（KE_BACKEND_CMD / 打包后端 / ke CLI）");
    let mut command = Command::new(&cmd);
    command.args(&args).env("KE_PORT", backend_port().to_string());

    if let Ok(log_dir) = app.path().app_log_dir() {
        let _ = std::fs::create_dir_all(&log_dir);
        let log_path = log_dir.join("backend.log");
        if let Ok(file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
        {
            if let Ok(err) = file.try_clone() {
                command.stdout(Stdio::from(file)).stderr(Stdio::from(err));
            }
        }
    }

    command.spawn()
}

/// 等待后端就绪（端口可连接）。
fn wait_backend_ready(port: u16) -> bool {
    let mut tries = 0;
    while tries < HEALTH_RETRIES {
        if is_up(port) {
            return true;
        }
        std::thread::sleep(HEALTH_INTERVAL);
        tries += 1;
    }
    false
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let port = backend_port();

            // 已有后端在监听（如用户手动 ke serve）则直接复用，避免重复拉起
            let child = if is_up(port) {
                None
            } else {
                match spawn_backend(&handle) {
                    Ok(c) => Some(c),
                    Err(e) => {
                        eprintln!("[desktop] 后端启动失败: {e}");
                        None
                    }
                }
            };
            app.manage(BackendState(Mutex::new(child)));

            if !wait_backend_ready(port) {
                eprintln!("[desktop] 等待后端就绪超时（127.0.0.1:{port}）");
            }

            if let Some(mut win) = app.get_webview_window("main") {
                let url = format!("http://127.0.0.1:{port}");
                // set_url 在当前 tauri v2 中已移除，用 eval 导航到后端面板
                if win
                    .eval(&format!(
                        "window.location.replace('{url}')"
                    ))
                    .is_ok()
                {
                    win.set_title(&format!("知识网络 · knowledge-engine（{url}）")).ok();
                }
            }

            // 注册全局快捷键：剪贴板采集。handler 持有 AppHandle 以便读剪贴板
            let h = app.handle().clone();
            app.global_shortcut()
                .on_shortcut(capture_shortcut(), move |_app, _shortcut, event| {
                    if event.state != ShortcutState::Pressed {
                        return;
                    }
                    // 读剪贴板文本，POST 到后端
                    use tauri_plugin_clipboard_manager::ClipboardExt;
                    match h.clipboard().read_text() {
                        Ok(text) if !text.trim().is_empty() => {
                            post_clipboard_to_backend(backend_port(), &text);
                            if let Some(win) = h.get_webview_window("main") {
                                let _ = win.set_focus();
                            }
                        }
                        _ => {}
                    }
                })
                .expect("注册全局快捷键失败（可能快捷键被其他应用占用）");

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // 退出时回收本进程拉起的后端
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app_handle.try_state::<BackendState>() {
                    if let Some(mut child) = state.0.lock().map(|mut g| g.take()).unwrap_or(None) {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        });
}
