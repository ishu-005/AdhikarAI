#!/usr/bin/env python
"""
AdhikarAI - One-command startup script

This script handles the complete setup and launch:
  1. Validates environment & dependencies
  2. Checks Supabase connection & migration
  3. Downloads & ingests legal documents (if --download flag)
  4. Starts the backend server
  5. Optionally launches the frontend dev server

Usage:
  python run.py                 # start backend only (assumes data already ingested)
  python run.py --download      # download acts from India Code + ingest + start backend
  python run.py --frontend      # start backend + frontend dev server
  python run.py --full          # everything (download, ingest, backend, frontend)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def log(msg: str, level: str = "INFO") -> None:
    """Print timestamped log message."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level:8s}] {msg}", flush=True)


def _project_venv_python(root: Path = PROJECT_ROOT) -> Path | None:
    """Return the project virtualenv Python executable if it exists."""
    if sys.platform.startswith("win"):
        candidate = root / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = root / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else None


def _should_reexec_into_venv(root: Path, current_python: Path) -> bool:
    venv_python = _project_venv_python(root)
    if venv_python is None:
        return False
    try:
        return venv_python.resolve() != current_python.resolve()
    except OSError:
        return True


def _ensure_project_venv() -> None:
    """Restart this launcher inside .venv so child processes use project deps."""
    if not _should_reexec_into_venv(PROJECT_ROOT, Path(sys.executable)):
        return
    venv_python = _project_venv_python(PROJECT_ROOT)
    if venv_python is None:
        return
    log(f"Switching to project virtualenv: {venv_python}", "INFO")
    raise SystemExit(subprocess.call([str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]]))


def check_env() -> bool:
    """Validate required environment variables."""
    from dotenv import load_dotenv

    log("Checking environment variables...")
    load_dotenv()

    required = ["SUPABASE_URL", "SUPABASE_API_KEY", "GROQ_API_KEY"]
    missing = [v for v in required if not os.getenv(v)]

    if missing:
        log(f"Missing environment variables: {', '.join(missing)}", "ERROR")
        log("Please create .env file from .env.example and fill in the values", "ERROR")
        return False

    log(f"OK Environment OK (Supabase URL: {os.getenv('SUPABASE_URL')[:50]}...)", "OK")
    return True


def check_supabase() -> bool:
    """Check Supabase connectivity."""
    if os.getenv("ADHIKARAI_SKIP_SUPABASE_CHECK", "").strip().lower() in {"1", "true", "yes"}:
        log("Skipping Supabase connection check (ADHIKARAI_SKIP_SUPABASE_CHECK=1).", "WARN")
        return False

    log("Checking Supabase connection...")
    url = os.getenv("SUPABASE_URL")
    api_key = os.getenv("SUPABASE_API_KEY")

    if not url or not api_key:
        log("Supabase credentials not set", "WARN")
        return False

    timeout = float(os.getenv("ADHIKARAI_SUPABASE_CHECK_TIMEOUT", "8"))
    code = """
import os
from supabase import create_client

client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_API_KEY"])
client.table("legal_documents").select("id").limit(1).execute()
print("ok", flush=True)
""".strip()

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            message = detail[-1] if detail else f"exit code {result.returncode}"
            raise RuntimeError(message)
        log("OK Supabase connected", "OK")
        return True
    except subprocess.TimeoutExpired:
        log(f"Supabase check timed out after {timeout:g}s; continuing startup.", "WARN")
        log("Set ADHIKARAI_SKIP_SUPABASE_CHECK=1 to skip this validation.", "WARN")
        return False
    except Exception as exc:
        log(f"Supabase check failed: {exc}", "WARN")
        log("Run the Supabase migration manually in SQL Editor: supabase_migration.sql", "WARN")
        return False


def run_download(download: bool) -> bool:
    """Download acts from India Code if --download flag is set."""
    if not download:
        return True

    log("Downloading authoritative acts from India Code...")
    try:
        from backend.ingest.download import main as download_acts

        download_acts()
        log("OK Download complete", "OK")
        return True
    except Exception as exc:
        log(f"Download failed: {exc}", "ERROR")
        return False


def run_ingest() -> bool:
    """Ingest PDFs into Supabase."""
    log("Ingesting PDFs (section-aware chunking, embedding, storage)...")
    try:
        from backend.core.logging import configure_logging
        from backend.ingest.pdf import ingest_all_pdfs
        from backend.ingest.web import crawl_dynamic_sources

        configure_logging()
        ingest_all_pdfs("./pdfs")
        log("Crawling dynamic web sources...")
        crawl_dynamic_sources()
        log("OK Ingestion complete", "OK")
        return True
    except Exception as exc:
        log(f"Ingestion failed: {exc}", "ERROR")
        return False


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _pick_port(preferred: int) -> int:
    """Return the preferred port, or the next free one, warning if it moved."""
    for candidate in range(preferred, preferred + 10):
        if not _port_in_use(candidate):
            if candidate != preferred:
                log(f"Port {preferred} is busy; using {candidate} instead.", "WARN")
            return candidate
    log(f"Ports {preferred}-{preferred + 9} all busy.", "ERROR")
    return preferred


def start_backend(host: str = "0.0.0.0", port: int = 8000) -> subprocess.Popen:
    """Start FastAPI backend server."""
    log(f"Starting backend on {host}:{port}...")
    log(f"Backend will serve UI at http://127.0.0.1:{port}")
    log("API endpoints: /api/query, /api/query/stream, /api/upload-pdf, /api/metrics, etc.")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        text=True,
    )
    time.sleep(2)  # Give the server time to start
    if proc.poll() is None:
        log("OK Backend started", "OK")
    else:
        log("Backend failed to start", "ERROR")
        return None
    return proc


def start_frontend() -> subprocess.Popen:
    """Start Next.js development server."""
    log("Starting frontend dev server on http://localhost:3000...")
    log("Frontend will proxy /api to http://127.0.0.1:8000")

    frontend_dir = Path("frontend-next")
    if not (frontend_dir / "node_modules").exists():
        log("Installing frontend dependencies (npm install)...", "WARN")
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)

    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=frontend_dir,
        text=True,
    )
    time.sleep(3)
    if proc.poll() is None:
        log("OK Frontend dev server started", "OK")
    else:
        log("Frontend failed to start", "WARN")
        return None
    return proc


def main() -> int:
    """Main entrypoint."""
    _ensure_project_venv()
    log("=== AdhikarAI Startup ===")

    download = "--download" in sys.argv
    frontend = "--frontend" in sys.argv or "--full" in sys.argv
    do_download = "--download" in sys.argv or "--full" in sys.argv

    # --port N (defaults to PORT env, else 8000); auto-bumps if busy.
    requested_port = int(os.getenv("PORT", "8000"))
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            requested_port = int(sys.argv[idx + 1])

    # Phase 1: Validate
    log("Phase 1: Validation", "HEADER")
    if not check_env():
        return 1
    check_supabase()  # Non-fatal if fails

    # Phase 2: Setup (optional)
    if do_download:
        log("Phase 2: Download & Ingest", "HEADER")
        if not run_download(do_download):
            log("Download failed, continuing with existing PDFs...", "WARN")
        if not run_ingest():
            log("Ingest failed, but backend can still run", "WARN")
    else:
        log("Phase 2: Skipped (use --download to fetch acts from India Code)", "WARN")

    # Phase 3: Start services
    log("Phase 3: Starting services", "HEADER")
    port = _pick_port(requested_port)
    backend_proc = start_backend(port=port)
    if backend_proc is None:
        return 1

    frontend_proc = None
    if frontend:
        frontend_proc = start_frontend()

    # Phase 4: Ready
    log("Phase 4: Ready", "HEADER")
    log("", "")
    log("OK AdhikarAI is running!", "OK")
    log("", "")
    log(f"  Backend:  http://127.0.0.1:{port}", "INFO")
    if frontend:
        log("  Frontend: http://localhost:3000  (with hot reload)", "INFO")
    log("", "")
    log("Ask a legal question in English or Hindi.", "INFO")
    log("Watch token-by-token streaming, citations, and live web sources.", "INFO")
    log("", "")
    log("Press Ctrl+C to stop all services.", "INFO")

    try:
        # Keep the processes alive
        while True:
            if backend_proc.poll() is not None:
                log("Backend process exited", "ERROR")
                if frontend_proc:
                    frontend_proc.terminate()
                return 1
            if frontend_proc and frontend_proc.poll() is not None:
                log("Frontend process exited (backend still running)", "WARN")
                frontend_proc = None
            time.sleep(1)
    except KeyboardInterrupt:
        log("Shutting down...", "INFO")
        backend_proc.terminate()
        if frontend_proc:
            frontend_proc.terminate()
        backend_proc.wait(timeout=5)
        if frontend_proc:
            frontend_proc.wait(timeout=5)
        log("Goodbye!", "OK")
        return 0


if __name__ == "__main__":
    sys.exit(main())
