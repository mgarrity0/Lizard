//! Directory watcher that emits `patterns-changed` events to the frontend.
//!
//! Debounced via `notify-debouncer-full` so fast successive saves collapse to
//! a single event. The watcher runs on a dedicated thread and lives for the
//! lifetime of the app (we intentionally leak the debouncer; stopping only
//! matters at process exit, and the OS handles that).

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use notify::{EventKind, RecursiveMode};
use notify_debouncer_full::new_debouncer;
use once_cell::sync::OnceCell;
use serde::Serialize;
use tauri::{AppHandle, Emitter};

const DEBOUNCE: Duration = Duration::from_millis(200);

static WATCHER: OnceCell<Mutex<Option<WatcherHandle>>> = OnceCell::new();

struct WatcherHandle {
    path: PathBuf,
    // Keep the debouncer alive so the watcher thread keeps running. The
    // underlying `Debouncer` is !Send + !Sync on some platforms, so we wrap
    // it in a Mutex and only access it from the lock holder.
    _debouncer: Box<dyn std::any::Any + Send>,
}

#[derive(Clone, Serialize)]
struct ChangedPayload {
    kind: &'static str,
    paths: Vec<String>,
}

pub fn ensure(app: &AppHandle, path: PathBuf) -> Result<(), String> {
    let cell = WATCHER.get_or_init(|| Mutex::new(None));
    let mut slot = cell.lock().map_err(|e| e.to_string())?;
    if let Some(existing) = slot.as_ref() {
        if existing.path == path {
            return Ok(());
        }
    }
    // Replace whatever was there (drops the old debouncer -> old thread exits).
    *slot = None;

    if !path.exists() {
        std::fs::create_dir_all(&path)
            .map_err(|e| format!("create {}: {e}", path.display()))?;
    }

    let app_for_cb = app.clone();
    let mut debouncer = new_debouncer(DEBOUNCE, None, move |res: notify_debouncer_full::DebounceEventResult| {
        match res {
            Ok(events) => {
                let mut paths = Vec::new();
                for ev in events {
                    if !matches!(
                        ev.event.kind,
                        EventKind::Create(_) | EventKind::Modify(_) | EventKind::Remove(_)
                    ) {
                        continue;
                    }
                    for p in &ev.event.paths {
                        paths.push(p.to_string_lossy().to_string());
                    }
                }
                if paths.is_empty() {
                    return;
                }
                let payload = ChangedPayload { kind: "changed", paths };
                if let Err(e) = app_for_cb.emit("patterns-changed", payload) {
                    log::warn!("emit patterns-changed failed: {e}");
                }
            }
            Err(errs) => {
                for e in errs {
                    log::warn!("watcher error: {e}");
                }
            }
        }
    })
    .map_err(|e| format!("create watcher: {e}"))?;

    debouncer
        .watch(&path, RecursiveMode::NonRecursive)
        .map_err(|e| format!("watch {}: {e}", path.display()))?;

    *slot = Some(WatcherHandle {
        path,
        _debouncer: Box::new(debouncer),
    });
    Ok(())
}

#[tauri::command]
pub fn watch_patterns_dir(app: AppHandle, path: String) -> Result<(), String> {
    ensure(&app, PathBuf::from(path))
}
