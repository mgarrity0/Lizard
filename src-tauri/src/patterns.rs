//! Pattern file I/O commands exposed to the frontend.
//!
//! Patterns live in `<project_root>/patterns/*.{js,mjs}`. In dev the project
//! root is the parent of the Tauri CWD (`src-tauri/..`). In a future bundled
//! release we'll switch to a user config dir; keep this logic encapsulated
//! inside `project_root()` so callers don't have to care.

use std::fs;
use std::path::{Path, PathBuf};

/// Resolve the Tessera project root.
///
/// Dev: the Tauri dev-server runs the Rust crate with CWD = `src-tauri/`;
/// walk up one level. Fallback: CWD.
pub fn resolve_project_root() -> PathBuf {
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    if cwd.file_name().and_then(|n| n.to_str()) == Some("src-tauri") {
        if let Some(parent) = cwd.parent() {
            return parent.to_path_buf();
        }
    }
    cwd
}

fn patterns_dir() -> PathBuf {
    resolve_project_root().join("patterns")
}

/// Guard: `name` must be a bare filename with no path separators or `..`.
fn validate_name(name: &str) -> Result<(), String> {
    if name.is_empty()
        || name.contains('/')
        || name.contains('\\')
        || name.contains("..")
        || Path::new(name).file_name().map(|s| s.to_string_lossy().to_string()) != Some(name.to_string())
    {
        return Err(format!("invalid pattern name: {name}"));
    }
    let ext = Path::new(name)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("");
    if !matches!(ext, "js" | "mjs") {
        return Err(format!("pattern must be .js or .mjs: {name}"));
    }
    Ok(())
}

#[tauri::command]
pub fn project_root() -> Result<String, String> {
    Ok(resolve_project_root().to_string_lossy().to_string())
}

#[tauri::command]
pub fn list_patterns() -> Result<Vec<String>, String> {
    let dir = patterns_dir();
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    for entry in fs::read_dir(&dir).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();
        if ext == "js" || ext == "mjs" {
            if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                out.push(name.to_string());
            }
        }
    }
    out.sort();
    Ok(out)
}

#[tauri::command]
pub fn read_pattern(name: String) -> Result<String, String> {
    validate_name(&name)?;
    let path = patterns_dir().join(&name);
    fs::read_to_string(&path).map_err(|e| format!("read {}: {e}", path.display()))
}

#[tauri::command]
pub fn write_pattern(name: String, content: String) -> Result<String, String> {
    validate_name(&name)?;
    let dir = patterns_dir();
    fs::create_dir_all(&dir).map_err(|e| format!("mkdir {}: {e}", dir.display()))?;
    let path = dir.join(&name);
    fs::write(&path, content.as_bytes())
        .map_err(|e| format!("write {}: {e}", path.display()))?;
    Ok(path.to_string_lossy().to_string())
}
