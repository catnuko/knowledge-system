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

/// 按优先级解析后端启动命令。
fn resolve_backend_command(app: &tauri::AppHandle) -> Option<(PathBuf, Vec<String>)> {
    // 1. 显式指定（可执行文件路径）
    if let Ok(cmd) = std::env::var("KE_BACKEND_CMD") {
        let cmd = cmd.trim();
        if !cmd.is_empty() {
            return Some((PathBuf::from(cmd), Vec::new()));
        }
    }
    // 2. 随包分发的 PyInstaller 单文件后端
    if let Ok(dir) = app.path().resource_dir() {
        let bundled = dir.join("knowledge-engine-backend");
        if bundled.is_file() {
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
                if win.set_url(url.parse().expect("后端 URL 解析失败")).is_ok() {
                    win.set_title(&format!("知识网络 · knowledge-engine（{url}）")).ok();
                }
            }
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
