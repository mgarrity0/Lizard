//! Python sidecar supervisor.
//!
//! Startup handshake:
//!   1. Pick a free TCP port on 127.0.0.1 by binding a listener to `:0`, read
//!      the assigned port, close the listener. There's a tiny race window
//!      before the child binds — acceptable for a local-only dev tool.
//!   2. Spawn `python -m tessera.api --port <port>` with PYTHONUTF8=1.
//!   3. Read lines from the child's stdout until we see `TESSERA_READY` or we
//!      time out after ~10 s.
//!   4. Kill the child on drop.

use anyhow::{anyhow, Context, Result};
use std::io::{BufRead, BufReader};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

const READY_MARKER: &str = "TESSERA_READY";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(10);

pub struct SidecarHandle {
    child: Option<Child>,
    port: u16,
}

impl SidecarHandle {
    pub fn base_url(&self) -> String {
        format!("http://127.0.0.1:{}", self.port)
    }
}

impl Drop for SidecarHandle {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

pub fn spawn(_app_dir: &Path) -> Result<SidecarHandle> {
    let port = pick_free_port().context("pick free port")?;

    let (python, args) = resolve_sidecar_cmd()?;
    let mut cmd = Command::new(&python);
    cmd.args(&args)
        .arg("--port")
        .arg(port.to_string())
        .env("PYTHONUTF8", "1")
        .env("PYTHONUNBUFFERED", "1")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    log::info!("spawning sidecar: {:?} {:?} --port {}", python, args, port);
    let mut child = cmd.spawn().with_context(|| {
        format!(
            "failed to spawn python sidecar at {:?}. Is the venv set up? (cd geometry && uv sync)",
            python
        )
    })?;

    let stdout = child.stdout.take().ok_or_else(|| anyhow!("no stdout"))?;
    let stderr = child.stderr.take().ok_or_else(|| anyhow!("no stderr"))?;

    // Relay stderr to our own logger.
    thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().map_while(Result::ok) {
            log::warn!("[sidecar-stderr] {}", line);
        }
    });

    // Wait for the ready marker on stdout (on a worker thread, then signal via channel).
    let (tx, rx) = mpsc::channel::<Result<()>>();
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines().map_while(Result::ok) {
            log::info!("[sidecar] {}", line);
            if line.contains(READY_MARKER) {
                let _ = tx.send(Ok(()));
                // Keep relaying the rest of stdout.
                continue;
            }
        }
    });

    match rx.recv_timeout(STARTUP_TIMEOUT) {
        Ok(Ok(())) => Ok(SidecarHandle {
            child: Some(child),
            port,
        }),
        Ok(Err(e)) => {
            let _ = child.kill();
            Err(e)
        }
        Err(_) => {
            let _ = child.kill();
            Err(anyhow!(
                "sidecar did not report ready within {:?}",
                STARTUP_TIMEOUT
            ))
        }
    }
}

fn pick_free_port() -> Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

/// Resolve the sidecar command.
///
/// Priority:
///   1. `TESSERA_SIDECAR_PYTHON` env var (full path to python.exe or python3)
///   2. Dev venv at `<repo-root>/geometry/.venv/Scripts/python.exe` (Windows)
///      or `<repo-root>/geometry/.venv/bin/python` (Unix). We walk up from the
///      cwd looking for `geometry/pyproject.toml`.
///   3. (Future) PyInstaller-bundled binary next to the Tauri exe.
fn resolve_sidecar_cmd() -> Result<(PathBuf, Vec<String>)> {
    let module_args = vec!["-m".to_string(), "tessera.api".to_string()];

    if let Ok(env_python) = std::env::var("TESSERA_SIDECAR_PYTHON") {
        return Ok((PathBuf::from(env_python), module_args));
    }

    if let Some(venv_py) = find_dev_venv_python()? {
        return Ok((venv_py, module_args));
    }

    Err(anyhow!(
        "could not locate python sidecar. Set TESSERA_SIDECAR_PYTHON or run `cd geometry && uv sync` to create the dev venv."
    ))
}

fn find_dev_venv_python() -> Result<Option<PathBuf>> {
    let mut dir: PathBuf = std::env::current_dir()?;
    for _ in 0..6 {
        let candidate_py = if cfg!(windows) {
            dir.join("geometry/.venv/Scripts/python.exe")
        } else {
            dir.join("geometry/.venv/bin/python")
        };
        if candidate_py.exists() {
            return Ok(Some(candidate_py));
        }
        if !dir.pop() {
            break;
        }
    }
    Ok(None)
}
