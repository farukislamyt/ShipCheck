from pathlib import Path

from typer.testing import CliRunner

from shipcheck.cli import _deployment_provider, _env_status, _framework, _provider_validation, _secret_findings, app, calculate_score, check_project, is_deployable

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
    source.write_text('AWS_ACCESS_KEY = "AKIA1234567890ABCDEF"\n', encoding="utf-8")
    findings = _secret_findings(tmp_path)
    assert any("AWS access key" in finding for finding in findings)


def test_secret_scanner_detects_provider_credentials(tmp_path: Path) -> None:
    source = tmp_path / "config.py"
    source.write_text(
        'GOOGLE = "AIzaSyA123456789012345678901234567890123"\n'
        'SLACK = "xoxb-1234567890-abcdefghijk"\n'
        'STRIPE = "sk_live_1234567890abcdef"\n',
        encoding="utf-8",
    )
    findings = _secret_findings(tmp_path)
    assert any("Google API key" in finding for finding in findings)
    assert any("Slack token" in finding for finding in findings)
    assert any("Stripe live key" in finding for finding in findings)


def test_secret_scanner_ignores_venv_and_build_artifacts(tmp_path: Path) -> None:
    for dirname in (".venv", "node_modules", "dist", "build", ".git"):
        ignored = tmp_path / dirname / "secrets.py"
        ignored.parent.mkdir()
        ignored.write_text('TOKEN = "ghp_123456789012345678901234567890"', encoding="utf-8")
    assert _secret_findings(tmp_path) == []


def test_secret_scanner_deduplicates_findings(tmp_path: Path) -> None:
    source = tmp_path / "config.py"
    source.write_text('TOKEN = "ghp_123456789012345678901234567890"\n', encoding="utf-8")
    assert _secret_findings(tmp_path) == ["config.py: GitHub token"]


def test_secret_scanner_ignores_short_generic_values(tmp_path: Path) -> None:
    source = tmp_path / "config.py"
    source.write_text('API_KEY = "example-placeholder"\n', encoding="utf-8")
    assert _secret_findings(tmp_path) == []


def test_weighted_score_uses_check_weights() -> None:
    checks = [("Tests", "PASS"), ("README", "WARN")]
    assert calculate_score(checks) == 67


def test_secret_failure_blocks_deployment() -> None:
    checks = [("Secrets scan", "FAIL"), ("Tests", "PASS")]
    assert is_deployable(checks) is False


def test_threshold_blocks_low_score() -> None:
    checks = [("Tests", "PASS"), ("README", "WARN")]
    assert is_deployable(checks, score=75, threshold=80) is False
    assert is_deployable(checks, score=75, threshold=70) is True


def test_deployment_provider_detection(tmp_path: Path) -> None:
    (tmp_path / "vercel.json").write_text("{}", encoding="utf-8")
    assert _deployment_provider(tmp_path) == "Vercel"

    (tmp_path / "vercel.json").unlink()
    (tmp_path / "Dockerfile").write_text("FROM python:3.11", encoding="utf-8")
    assert _deployment_provider(tmp_path) == "Docker"

    (tmp_path / "Dockerfile").unlink()
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI", encoding="utf-8")
    assert _deployment_provider(tmp_path) == "GitHub Actions"


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
    workflow.write_text("name: Deploy\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n", encoding="utf-8")
    assert _provider_validation(tmp_path, "GitHub Actions") == "FAIL"


def test_provider_validation_is_reported_and_weighted(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("CMD [\"python\", \"app.py\"]", encoding="utf-8")
    results = dict(check_project(tmp_path))
    assert results["Provider validation"] == "FAIL"
    assert calculate_score([("Provider validation", "PASS")]) == 100


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


def test_json_output_includes_provider(tmp_path: Path) -> None:
    (tmp_path / "vercel.json").write_text("{}", encoding="utf-8")
    result = runner.invoke(app, [str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert '"deployment_provider": "Vercel"' in result.stdout
