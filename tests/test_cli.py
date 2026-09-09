from pathlib import Path

from shipcheck.cli import _env_status, _framework, _secret_findings, check_project


def test_project_checks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# Demo", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("__pycache__/", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["typer"]\n', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()

    results = dict(check_project(tmp_path))

    assert results["Project directory"] == "PASS"
    assert results["Git repository"] == "PASS"
    assert results["README"] == "PASS"
    assert results[".gitignore"] == "PASS"
    assert results["Dependency manifest"] == "PASS"
    assert results["Tests"] == "PASS"


def test_framework_detection(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi>=0.1", encoding="utf-8")
    assert _framework(tmp_path) == "FastAPI"


def test_environment_template_requires_matching_keys(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("DATABASE_URL=\nAPI_KEY=\n", encoding="utf-8")
    (tmp_path / ".env").write_text("DATABASE_URL=test\n", encoding="utf-8")
    assert _env_status(tmp_path) == "WARN"

    (tmp_path / ".env").write_text("DATABASE_URL=test\nAPI_KEY=test\n", encoding="utf-8")
    assert _env_status(tmp_path) == "PASS"


def test_secret_scanner_detects_common_secret(tmp_path: Path) -> None:
    source = tmp_path / "config.py"
    source.write_text('AWS_ACCESS_KEY = "AKIA1234567890ABCDEF"\n', encoding="utf-8")
    findings = _secret_findings(tmp_path)
    assert any("AWS access key" in finding for finding in findings)


def test_secret_scanner_ignores_venv(tmp_path: Path) -> None:
    ignored = tmp_path / ".venv" / "lib.py"
    ignored.parent.mkdir()
    ignored.write_text('TOKEN = "ghp_123456789012345678901234567890"', encoding="utf-8")
    assert _secret_findings(tmp_path) == []
