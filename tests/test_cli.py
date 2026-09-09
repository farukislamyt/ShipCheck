from pathlib import Path

from shipcheck.cli import check_project


def test_project_checks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# Demo")
    (tmp_path / ".gitignore").write_text("__pycache__/")

    results = dict(check_project(tmp_path))

    assert results["Project directory"] == "PASS"
    assert results["Git repository"] == "PASS"
    assert results["README"] == "PASS"
    assert results[".gitignore"] == "PASS"
    assert results["Environment template"] == "WARN"
