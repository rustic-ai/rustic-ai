"""Test-runner cleanup must terminate owned children without signaling its caller."""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runner_repository(tmp_path):
    root = tmp_path / "repository"
    (root / "scripts").mkdir(parents=True)
    for name in ("run_tests_no_coverage.sh", "run_all_tests.sh", "run_in_session.py"):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(sys.executable)
    stub = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import signal
import sys
import time

name = Path(sys.argv[0]).name
if name == 'ps':
    print(os.getpgid(int(sys.argv[sys.argv.index('-p') + 1])))
    sys.exit(0)
if name == 'sleep':
    if sys.argv[1] != '5':
        time.sleep(float(sys.argv[1]))
    sys.exit(0)
if name in ('pkill', 'lsof'):
    Path('unsafe-cleanup').write_text(name)
    sys.exit(1)
role = 'server' if name == 'opentelemetry-instrument' else 'pytest'
def stop(signum, frame):
    Path(role + '.stopped').write_text(str(signum))
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
Path(role + '.json').write_text(json.dumps({'pid': os.getpid(), 'sid': os.getsid(0), 'pgid': os.getpgid(0)}))
if role == 'pytest' and not os.environ['TEST_MODE'].startswith('interrupt'):
    # Wait for the fake server to register before the tests finish.
    deadline = time.monotonic() + 3
    while not Path('server.json').exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    sys.exit(int(os.environ['TEST_MODE']))
while True:
    time.sleep(0.01)
"""
    for name in ("pytest", "coverage", "opentelemetry-instrument", "sleep", "pkill", "lsof", "ps"):
        path = bin_dir / name
        path.write_text(stub)
        path.chmod(0o755)
    env = os.environ | {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
    return root, env


GUARDIAN = """
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

# A background shell can pass ignored SIGINT through pytest. Model an ordinary
# caller so the nested runner can install its interrupt trap in either context.
signal.signal(signal.SIGINT, signal.SIG_DFL)
signal.signal(signal.SIGTERM, signal.SIG_DFL)
with Path('runner.log').open('w') as log:
    child = subprocess.Popen(['sh', 'scripts/' + sys.argv[1], '--no-parallel'], stdout=log, stderr=log)
    if os.environ['TEST_MODE'].startswith('interrupt'):
        deadline = time.monotonic() + 5
        while not (Path('pytest.json').exists() and Path('server.json').exists()):
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Test runner did not start')
            time.sleep(0.01)
        child.send_signal(signal.SIGINT if os.environ['TEST_MODE'] == 'interrupt_int' else signal.SIGTERM)
    code = child.wait(timeout=5)
Path('result.json').write_text(json.dumps({'code': code, 'sid': os.getsid(0), 'pgid': os.getpgid(0)}))
"""


@pytest.mark.parametrize("script", ["run_tests_no_coverage.sh", "run_all_tests.sh"])
@pytest.mark.parametrize("mode", ["0", "7", "interrupt", "interrupt_int"])
def test_cleanup_preserves_caller_and_exit_status(runner_repository, script, mode):
    root, env = runner_repository
    # Contain the old broken cleanup in a disposable session; it must never be
    # able to signal the real pytest process or the user's processes.
    guardian = subprocess.Popen(
        [sys.executable, "-c", GUARDIAN, script],
        cwd=root,
        env=env | {"TEST_MODE": mode},
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert guardian.wait(timeout=12) == 0, (root / "runner.log").read_text()
        result = json.loads((root / "result.json").read_text())
        worker = json.loads((root / "pytest.json").read_text())
        server = json.loads((root / "server.json").read_text())
        expected_code = {"interrupt": 143, "interrupt_int": 130}.get(mode)
        assert result["code"] == (int(mode) if expected_code is None else expected_code)
        assert worker["sid"] == server["sid"] != result["sid"]
        assert worker["pgid"] == server["pgid"] != result["pgid"]
        assert (root / "server.stopped").exists(), "The owned server must be shut down"
        assert not (root / "unsafe-cleanup").exists(), "Cleanup must target owned processes only"
    finally:
        groups = {guardian.pid}
        for role in ("server", "pytest"):
            metadata = root / (role + ".json")
            if metadata.exists():
                groups.add(json.loads(metadata.read_text())["pgid"])
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        guardian.wait(timeout=5)
