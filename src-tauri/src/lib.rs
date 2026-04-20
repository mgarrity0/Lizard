//! Tessera — Tauri shell.
//!
//! Responsibilities:
//!   - Spawn the Python geometry sidecar (FastAPI) on an ephemeral localhost port
//!   - Expose `get_sidecar_base` to the React frontend so it can hit the HTTP API
//!   - Own pattern file I/O (list/read/write) + file-watch for hot-reload
//!   - Own hardware-IO modules (WLED UDP, serial) in later milestones
//!
//! The sidecar is spawned at app startup and killed on exit. In dev, we use the
//! uv-managed venv at `../geometry/.venv/Scripts/python.exe` on Windows (or
//! `.venv/bin/python` on Unix). In release, we expect a PyInstaller-bundled
//! `tessera-sidecar` binary adjacent to the Tauri executable (wired up via
//! `tauri.conf.json` `bundle.externalBin` — TODO in a later milestone).

mod patterns;
mod sidecar;
mod watch;

use once_cell::sync::OnceCell;
use sidecar::SidecarHandle;
use std::sync::Mutex;
use tauri::Manager;

static SIDECAR: OnceCell<Mutex<SidecarHandle>> = OnceCell::new();

#[tauri::command]
fn get_sidecar_base() -> Result<String, String> {
    let handle = SIDECAR
        .get()
        .ok_or_else(|| "sidecar not initialised".to_string())?;
    let lock = handle.lock().map_err(|e| e.to_string())?;
    Ok(lock.base_url())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Find the Python sidecar (dev venv or bundled exe) and start it.
            let app_dir = app
                .path()
                .resource_dir()
                .unwrap_or_else(|_| std::env::current_dir().expect("cwd"));
            let handle = sidecar::spawn(&app_dir)?;
            log::info!("sidecar ready at {}", handle.base_url());
            SIDECAR
                .set(Mutex::new(handle))
                .map_err(|_| "sidecar already set")?;

            // Auto-start the patterns watcher against <project_root>/patterns.
            // Frontend can still call watch_patterns_dir to retarget later.
            let patterns_path = patterns::resolve_project_root().join("patterns");
            if let Err(e) = watch::ensure(&app.handle(), patterns_path.clone()) {
                log::warn!("patterns watcher not started: {e}");
            } else {
                log::info!("watching patterns at {}", patterns_path.display());
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_sidecar_base,
            patterns::project_root,
            patterns::list_patterns,
            patterns::read_pattern,
            patterns::write_pattern,
            watch::watch_patterns_dir,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
