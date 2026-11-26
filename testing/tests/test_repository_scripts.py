"""Release helpers must preserve failures and publish only a fresh generation."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repository"
    (root / "scripts").mkdir(parents=True)
    for filename in ("run_on_each.sh", "poetry_build.sh", "replace_artifact_directory.py"):
        shutil.copyfile(ROOT / "scripts" / filename, root / "scripts" / filename)
    (root / "scripts/modules.sh").write_text('MODULES="alpha beta"\n')
    for module in ("alpha", "beta"):
        (root / module / "dist").mkdir(parents=True)
        (root / module / "dist" / "stale.whl").write_text("stale module artifact")
    (root / "bin").mkdir()
    poetry = root / "bin/poetry"
    poetry.write_text("""#!/usr/bin/env python3
import os
from pathlib import Path
import sys
module = Path.cwd().name
with Path(os.environ['INVOCATIONS']).open('a') as stream:
    stream.write(module + ':' + sys.argv[1] + '\\n')
if module == os.environ.get('FAIL_MODULE'):
    sys.exit(9)
if sys.argv[1] == 'build':
    target = Path(sys.argv[sys.argv.index('--output') + 1])
    target.mkdir(exist_ok=True)
    (target / (module + '-0.1-py3-none-any.whl')).write_text('new wheel')
    if not os.environ.get('MISSING_SDIST'):
        (target / (module + '-0.1.tar.gz')).write_text('new source')
""")
    poetry.chmod(0o755)
    env = os.environ | {
        "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
        "BUILD_PYTHON": sys.executable,
        "INVOCATIONS": str(root / "invocations"),
    }
    return root, env


def run(root, env, script, *args):
    return subprocess.run(["sh", str(root / "scripts" / script), *args], env=env, capture_output=True, text=True)


def test_module_runner_continues_and_reports_all_failures(repository):
    root, env = repository
    command = 'basename "$PWD" >> "../visited"; exit 7'
    result = run(root, env, "run_on_each.sh", command)
    assert result.returncode != 0
    assert (root / "visited").read_text().splitlines() == ["alpha", "beta"]
    assert "Failed modules: alpha beta" in result.stderr


def test_module_runner_succeeds_and_preserves_command_arguments(repository):
    root, env = repository
    result = run(root, env, "run_on_each.sh", 'printf "%s" "value with spaces" > result')
    assert result.returncode == 0
    assert all((root / module / "result").read_text() == "value with spaces" for module in ("alpha", "beta"))


def existing_distribution(root):
    dist = root / "dist"
    dist.mkdir()
    (dist / "retired-lancedb.whl").write_text("obsolete aggregate artifact")
    (dist / "notes.md").write_text("keep notes")
    (dist / "archive").mkdir()
    (dist / "archive/old-release.whl").write_text("keep archival release")
    return dist


def test_build_helper_publishes_only_fresh_artifacts_and_keeps_archives(repository):
    root, env = repository
    dist = existing_distribution(root)
    result = run(root, env, "poetry_build.sh")
    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in dist.iterdir()) == [
        "alpha-0.1-py3-none-any.whl",
        "alpha-0.1.tar.gz",
        "archive",
        "beta-0.1-py3-none-any.whl",
        "beta-0.1.tar.gz",
        "notes.md",
    ]
    assert (dist / "notes.md").read_text() == "keep notes"
    assert (dist / "archive/old-release.whl").read_text() == "keep archival release"
    assert not list(root.glob(".build-artifacts.*"))


@pytest.mark.parametrize("failure", ["module", "missing_archive"])
def test_build_failure_never_replaces_existing_distribution(repository, failure):
    root, env = repository
    dist = existing_distribution(root)
    env = env | ({"FAIL_MODULE": "beta"} if failure == "module" else {"MISSING_SDIST": "1"})
    result = run(root, env, "poetry_build.sh")
    assert result.returncode != 0
    assert (dist / "retired-lancedb.whl").read_text() == "obsolete aggregate artifact"
    assert (dist / "archive/old-release.whl").read_text() == "keep archival release"
    assert sorted(path.name for path in dist.iterdir()) == ["archive", "notes.md", "retired-lancedb.whl"]
    assert not list(root.glob(".build-artifacts.*"))


def test_build_helper_supports_first_build_and_skipped_modules(repository):
    root, env = repository
    result = run(root, env | {"SKIP_MODULE": "beta"}, "poetry_build.sh")
    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in (root / "dist").iterdir()) == ["alpha-0.1-py3-none-any.whl", "alpha-0.1.tar.gz"]
    assert (root / "invocations").read_text().splitlines() == ["alpha:install", "alpha:build"]
