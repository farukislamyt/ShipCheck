from pathlib import Path

from typer.testing import CliRunner

from shipcheck.cli import _env_status, _framework, _secret_findings, app, calculate_score, check_project, is_deployable

runner = CliRunner()


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


def test_weighted_score_uses_check_weights() -> None:
    checks = [("Tests", "PASS"), ("README", "WARN")]
    assert calculate_score(checks) == 75


def test_secret_failure_blocks_deployment() -> None:
    checks = [("Secrets scan", "FAIL"), ("Tests", "PASS")]
    assert is_deployable(checks) is False


def test_threshold_blocks_low_score() -> None:
    checks = [("Tests", "PASS"), ("README", "WARN")]
    assert is_deployable(checks, score=75, threshold=80) is False
    assert is_deployable(checks, score=75, threshold=70) is True


def test_gate_exits_nonzero_when_blocked(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--gate", "--json"])
    assert result.exit_code == 1


def test_cli_threshold_override(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--threshold", "0", "--json"])
    assert result.exit_code == 0
    assert '"threshold": 0' in result.stdout
    assert '"deployable": true' in result.stdout


def test_json_output_includes_deployable(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert '"deployable": true' in result.stdout
