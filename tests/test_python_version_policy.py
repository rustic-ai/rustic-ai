from pathlib import Path
import re
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REQUIRES_PYTHON = ">=3.13,<3.14"
EXPECTED_PYTHON_VERSION = "3.13.12"


def test_all_pyprojects_stay_on_python_313():
    mismatches = []

    for pyproject_path in sorted(REPO_ROOT.rglob("pyproject.toml")):
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        requires_python = pyproject.get("project", {}).get("requires-python")
        if requires_python != EXPECTED_REQUIRES_PYTHON:
            mismatches.append(f"{pyproject_path.relative_to(REPO_ROOT)} -> {requires_python}")

    assert not mismatches, "\n".join(mismatches)


def test_ci_and_docker_stay_pinned_to_python_313():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.13\.12-slim\b", dockerfile, re.MULTILINE)

    publish_docs = (REPO_ROOT / ".github/workflows/publish-docs.yml").read_text(encoding="utf-8")
    assert re.search(rf"python-version:\s*{re.escape(EXPECTED_PYTHON_VERSION)}\b", publish_docs)
