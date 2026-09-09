from pathlib import Path

from shipcheck.cli import _secret_findings, check_project


def test_secret_detection(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text('API_KEY = "super-secret-value-12345"')
    findings = _secret_findings(tmp_path)
    assert findings
    assert "Generic API key" in findings[0]


def test_dependency_and_tests_checks(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (tmp_path / "tests").mkdir()
    results = dict(check_project(tmp_path))
    assert results["Dependency manifest"] == "PASS"
    assert results["Tests"] == "PASS"
    assert results["Secrets scan"] == "PASS"
