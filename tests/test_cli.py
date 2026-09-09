from pathlib import Path

from typer.testing import CliRunner

from shipcheck.cli import (
    _deployment_provider,
    _env_status,
    _framework,
    _provider_validation,
    _secret_findings,
    app,
    calculate_score,
    check_project,
    is_deployable,
)

runner = CliRunner()


def test_project_checks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# Demo", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("__pycache__/", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["typer"]\n', encoding="utf-8")
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
    aws_key = "AKIA" + "1234567890ABCDEF"
    source.write_text(f'AWS_ACCESS_KEY = "{aws_key}"\n', encoding="utf-8")
    assert any("AWS access key" in finding for finding in _secret_findings(tmp_path))


def test_secret_scanner_detects_provider_credentials(tmp_path: Path) -> None:
    source = tmp_path / "config.py"
    google_key = "AIza" + "SyA12345678901234567890123456789012"
    slack_token = "xoxb-" + "1234567890-abcdefghijk"
    stripe_key = "sk_live_" + "1234567890abcdef"
    source.write_text(f'GOOGLE = "{google_key}"\nSLACK = "{slack_token}"\nSTRIPE = "{stripe_key}"\n', encoding="utf-8")
    findings = _secret_findings(tmp_path)
    assert any("Google API key" in finding for finding in findings)
    assert any("Slack token" in finding for finding in findings)
    assert any("Stripe live key" in finding for finding in findings)


def test_secret_scanner_ignores_venv_and_build_artifacts(tmp_path: Path) -> None:
    github_token = "ghp_" + "123456789012345678901234567890"
    for dirname in (".venv", "node_modules", "dist", "build", ".git"):
        ignored = tmp_path / dirname / "secrets.py"
        ignored.parent.mkdir()
        ignored.write_text(f'TOKEN = "{github_token}"', encoding="utf-8")
    assert _secret_findings(tmp_path) == []


def test_secret_scanner_deduplicates_findings(tmp_path: Path) -> None:
    source = tmp_path / "config.py"
    github_token = "ghp_" + "123456789012345678901234567890"
    source.write_text(f'TOKEN = "{github_token}"\n', encoding="utf-8")
    assert _secret_findings(tmp_path) == ["config.py: GitHub token"]


def test_secret_scanner_ignores_short_generic_values(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text('API_KEY = "example-placeholder"\n', encoding="utf-8")
    assert _secret_findings(tmp_path) == []


def test_weighted_score_uses_check_weights() -> None:
    assert calculate_score([("Tests", "PASS"), ("README", "WARN")]) == 67


def test_secret_failure_blocks_deployment() -> None:
    assert is_deployable([("Secrets scan", "FAIL"), ("Tests", "PASS")]) is False


def test_threshold_blocks_low_score() -> None:
    checks = [("Tests", "PASS"), ("README", "WARN")]
    assert is_deployable(checks, score=75, threshold=80) is False
    assert is_deployable(checks, score=75, threshold=70) is True


def test_deployment_provider_detection(tmp_path: Path) -> None:
    markers = (("vercel.json", "Vercel"), ("render.yaml", "Render"), ("railway.json", "Railway"), ("fly.toml", "Fly.io"), ("netlify.toml", "Netlify"), ("template.yaml", "AWS"))
    for filename, provider in markers:
        (tmp_path / filename).write_text("{}", encoding="utf-8")
        assert _deployment_provider(tmp_path) == provider
        (tmp_path / filename).unlink()
    (tmp_path / "Dockerfile").write_text("FROM python:3.11", encoding="utf-8")
    assert _deployment_provider(tmp_path) == "Docker"


def test_vercel_config_validation(tmp_path: Path) -> None:
    (tmp_path / "vercel.json").write_text('{"buildCommand": "npm run build"}', encoding="utf-8")
    assert _provider_validation(tmp_path, "Vercel") == "PASS"
    (tmp_path / "vercel.json").write_text('{invalid', encoding="utf-8")
    assert _provider_validation(tmp_path, "Vercel") == "FAIL"


def test_dockerfile_validation(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\nCMD [\"python\", \"app.py\"]", encoding="utf-8")
    assert _provider_validation(tmp_path, "Docker") == "PASS"
    (tmp_path / "Dockerfile").write_text("CMD [\"python\", \"app.py\"]", encoding="utf-8")
    assert _provider_validation(tmp_path, "Docker") == "FAIL"


def test_compose_yaml_validation(tmp_path: Path) -> None:
    (tmp_path / "compose.yml").write_text("services:\n  app:\n    image: python:3.11\n", encoding="utf-8")
    assert _provider_validation(tmp_path, "Docker") == "PASS"
    (tmp_path / "compose.yml").write_text("services:\n  app: [\n", encoding="utf-8")
    assert _provider_validation(tmp_path, "Docker") == "FAIL"


def test_github_actions_validation(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    workflow = workflows / "deploy.yml"
    workflow.write_text("name: Deploy\non: push\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
    assert _provider_validation(tmp_path, "GitHub Actions") == "PASS"
    workflow.write_text("name: Deploy\non: [push\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
    assert _provider_validation(tmp_path, "GitHub Actions") == "FAIL"


def test_provider_validation_is_reported_and_weighted(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("CMD [\"python\", \"app.py\"]", encoding="utf-8")
    results = dict(check_project(tmp_path))
    assert results["Provider validation"] == "FAIL"
    assert calculate_score([("Provider validation", "PASS")]) == 100


def test_config_ignore_and_threshold(tmp_path: Path) -> None:
    (tmp_path / ".shipcheck.toml").write_text('[shipcheck]\nthreshold = 90\n[shipcheck.ignore]\nchecks = ["Tests"]\npaths = ["fixtures/"]\n', encoding="utf-8")
    result = runner.invoke(app, [str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert '"threshold": 90' in result.stdout
    assert '"name": "Tests"' not in result.stdout


def test_invalid_config_returns_exit_code_2(tmp_path: Path) -> None:
    (tmp_path / ".shipcheck.toml").write_text("[shipcheck\n", encoding="utf-8")
    result = runner.invoke(app, [str(tmp_path), "--json"])
    assert result.exit_code == 2


def test_sarif_output(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--format", "sarif"])
    assert result.exit_code == 0
    assert '"version": "2.1.0"' in result.stdout
    assert '"name": "ShipCheck"' in result.stdout


def test_diagnostics_are_in_json(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert "diagnostics" in result.stdout
    assert "README" in result.stdout


def test_safe_fix_creates_gitignore(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--fix", "--json"])
    assert result.exit_code == 0
    assert (tmp_path / ".gitignore").exists()


def test_gate_exits_nonzero_when_blocked(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--gate", "--json"])
    assert result.exit_code == 1


def test_cli_threshold_override(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--threshold", "0", "--json"])
    assert result.exit_code == 0
    assert '"threshold": 0' in result.stdout
    assert '"deployable": true' in result.stdout


def test_json_output_is_blocked_for_empty_project(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert '"deployable": false' in result.stdout


def test_json_output_includes_provider(tmp_path: Path) -> None:
    (tmp_path / "vercel.json").write_text("{}", encoding="utf-8")
    result = runner.invoke(app, [str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert '"deployment_provider": "Vercel"' in result.stdout
