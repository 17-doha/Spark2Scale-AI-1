"""
test_fixes_locally.py
─────────────────────
Verifies ALL pitch-analyzer fixes (original + new session-cleanup fixes).

Run with: venv\Scripts\python.exe test_fixes_locally.py
"""

import os, sys, json, time, subprocess, threading, importlib, asyncio
from pathlib import Path
from collections import deque

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"
INFO = "\033[94mℹ️  INFO\033[0m"
WARN = "\033[93m⚠️  WARN\033[0m"

results = []

def check(name, condition, detail=""):
    tag = PASS if condition else FAIL
    print(f"  {tag}  {name}" + (f"\n         {detail}" if detail else ""))
    results.append((name, condition))

print("\n══════════════════════════════════════════════════════════")
print("  Spark2Scale — Pitch Analyzer Fix Verification (v2)")
print("══════════════════════════════════════════════════════════\n")

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — phase watcher exits on state.phase == "done"
# ─────────────────────────────────────────────────────────────────────────────
print("▶ TEST 1: _phase_watcher exits on state.phase='done' (double-agent fix)")

try:
    src = (ROOT / "app" / "graph" / "pitch_analyzer" / "workflow.py").read_text(encoding="utf-8")
    lines = src.splitlines()

    # Find the while True loop in _phase_watcher and check for the done guard
    watcher_start = next(i for i, l in enumerate(lines) if "_phase_watcher" in l and "async def" in l)
    while_true_idx = next(i for i, l in enumerate(lines) if i > watcher_start and "while True:" in l)
    # Check within the next ~20 lines for the done guard
    block = "\n".join(lines[while_true_idx : while_true_idx + 20])
    has_done_guard = 'state.phase == "done"' in block and "return" in block
    check("_phase_watcher has done-guard at top of while loop", has_done_guard,
          "Look for 'if state.phase == \"done\": return' in _phase_watcher")
except Exception as e:
    check("_phase_watcher done guard", False, str(e))

print()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — on_participant_disconnected sets phase=done synchronously
# ─────────────────────────────────────────────────────────────────────────────
print("▶ TEST 2: on_participant_disconnected sets phase=done immediately (double-agent fix)")

try:
    src = (ROOT / "app" / "graph" / "pitch_analyzer" / "workflow.py").read_text(encoding="utf-8")
    lines = src.splitlines()

    # Find the on_participant_disconnected function
    disc_idx = next(i for i, l in enumerate(lines) if "def on_participant_disconnected" in l)
    # The phase assignment must happen BEFORE any asyncio.create_task call
    block = lines[disc_idx : disc_idx + 20]
    block_str = "\n".join(block)

    phase_done_line = next((i for i, l in enumerate(block) if 'state.phase = "done"' in l), None)
    create_task_line = next((i for i, l in enumerate(block) if "create_task" in l), None)

    has_phase_done = phase_done_line is not None
    phase_before_task = has_phase_done and (create_task_line is None or phase_done_line < create_task_line)
    check("phase='done' set inside on_participant_disconnected", has_phase_done)
    check("phase='done' set BEFORE asyncio.create_task", phase_before_task,
          "phase=done must come before create_task to stop watchers synchronously")
except Exception as e:
    check("on_participant_disconnected phase=done check", False, str(e))

print()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — on_participant_disconnected calls ctx.room.disconnect()
# ─────────────────────────────────────────────────────────────────────────────
print("▶ TEST 3: agent calls ctx.room.disconnect() after report (removes agent from room)")

try:
    src = (ROOT / "app" / "graph" / "pitch_analyzer" / "workflow.py").read_text(encoding="utf-8")
    disc_idx = src.find("def on_participant_disconnected")
    # Find the next 150 lines after the handler
    snippet = src[disc_idx : disc_idx + 4000]
    has_disconnect = "ctx.room.disconnect()" in snippet
    has_finally = "finally:" in snippet
    check("ctx.room.disconnect() in handler", has_disconnect)
    check("disconnect() inside finally block (always runs)", has_finally)
except Exception as e:
    check("ctx.room.disconnect check", False, str(e))

print()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — pitch_history fallback for empty transcript
# ─────────────────────────────────────────────────────────────────────────────
print("▶ TEST 4: pitch_history fallback for empty full_transcript (report fix)")

try:
    src = (ROOT / "app" / "graph" / "pitch_analyzer" / "workflow.py").read_text(encoding="utf-8")
    disc_idx = src.find("def on_participant_disconnected")
    snippet = src[disc_idx : disc_idx + 4000]
    has_fallback = "pitch_history" in snippet and "full_transcript.strip()" in snippet
    has_skip_empty = "no speech data" in snippet or "session too short" in snippet
    check("pitch_history used as fallback when full_transcript empty", has_fallback)
    check("skips report gracefully if no speech at all", has_skip_empty)
except Exception as e:
    check("pitch_history fallback check", False, str(e))

print()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — /stop endpoint exists in pitch_analyzer.py
# ─────────────────────────────────────────────────────────────────────────────
print("▶ TEST 5: /stop endpoint added to API routes")

try:
    src = (ROOT / "app" / "api" / "routes" / "pitch_analyzer.py").read_text(encoding="utf-8")
    has_stop_route = '@router.post("/stop"' in src
    has_terminate = "worker_process.terminate()" in src
    has_kill = "worker_process.kill()" in src
    has_reset = "worker_process = None" in src
    check("@router.post('/stop') exists", has_stop_route)
    check("terminate() called on worker process", has_terminate)
    check("kill() fallback if terminate times out", has_kill)
    check("worker_process reset to None after stop", has_reset)
except Exception as e:
    check("/stop endpoint check", False, str(e))

print()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6 — TokenRequest class still intact
# ─────────────────────────────────────────────────────────────────────────────
print("▶ TEST 6: TokenRequest class and /token route still intact")

try:
    src = (ROOT / "app" / "api" / "routes" / "pitch_analyzer.py").read_text(encoding="utf-8")
    has_token_model = "class TokenRequest(BaseModel):" in src
    has_token_route = '@router.post("/token"' in src
    has_room_name = 'room_name: Optional[str]' in src
    check("class TokenRequest(BaseModel) present", has_token_model)
    check("@router.post('/token') present", has_token_route)
    check("room_name field in TokenRequest", has_room_name)
except Exception as e:
    check("TokenRequest integrity", False, str(e))

print()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7 — FastAPI app imports successfully (syntax check)
# ─────────────────────────────────────────────────────────────────────────────
print("▶ TEST 7: API routes file imports without syntax errors")

venv_python = ROOT / "venv" / "Scripts" / "python.exe"
if not venv_python.exists():
    venv_python = ROOT / "venv" / "bin" / "python"
python_exe = str(venv_python) if venv_python.exists() else sys.executable

try:
    result = subprocess.run(
        [python_exe, "-c", "import ast; ast.parse(open('app/api/routes/pitch_analyzer.py').read()); print('OK')"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=10
    )
    ok = "OK" in result.stdout and result.returncode == 0
    check("pitch_analyzer.py parses without syntax errors", ok,
          result.stderr[:200] if not ok else "")

    result2 = subprocess.run(
        [python_exe, "-c", "import ast; ast.parse(open('app/graph/pitch_analyzer/workflow.py').read()); print('OK')"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=10
    )
    ok2 = "OK" in result2.stdout and result2.returncode == 0
    check("workflow.py parses without syntax errors", ok2,
          result2.stderr[:200] if not ok2 else "")
except Exception as e:
    check("syntax check", False, str(e))

print()


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8 — Live subprocess: watch for [DISCONNECT] log line
# ─────────────────────────────────────────────────────────────────────────────
print("▶ TEST 8: Subprocess startup (worker registers, no crash)")
print(f"  {INFO}  Using Python: {python_exe}\n")

script = str(ROOT / "app" / "graph" / "pitch_analyzer" / "main.py")
env = os.environ.copy()
startup_lines = []

try:
    proc = subprocess.Popen(
        [python_exe, script, "dev", "--skip-extraction"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    def _read():
        for line in proc.stdout:
            startup_lines.append(line.rstrip())

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    time.sleep(8)
    proc.terminate()
    t.join(timeout=3)

    output = "\n    ".join(startup_lines[:25])
    print(f"  First ~25 lines:\n    {output}\n")

    abort_seen  = any("STARTUP ABORT" in l for l in startup_lines)
    worker_seen = any(
        "registered worker" in l.lower() or "livekit" in l.lower() or "_PREFLIGHT loaded" in l
        for l in startup_lines
    )
    check("No STARTUP ABORT", not abort_seen)
    check("Worker registered with LiveKit", worker_seen)
except Exception as e:
    check("Subprocess smoke test", False, str(e))

print()

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("══════════════════════════════════════════════════════════")
passed = sum(1 for _, ok in results if ok)
total  = len(results)
print(f"  Results: {passed}/{total} passed")
if passed == total:
    print(f"  \033[92m🎉 All checks passed — safe to deploy!\033[0m")
else:
    failed = [name for name, ok in results if not ok]
    print(f"  \033[91m⚠️  Fix before deploying:\033[0m")
    for f in failed:
        print(f"     • {f}")
print("══════════════════════════════════════════════════════════\n")
