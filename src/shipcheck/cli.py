from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Pre-deployment health checks for software projects.")
console = Console()


def check_project(path: Path) -> list[tuple[str, str]]:
    checks: list[tuple[str, str]] = []
    checks.append(("Project directory", "PASS" if path.is_dir() else "FAIL"))
    checks.append(("Git repository", "PASS" if (path / ".git").exists() else "WARN"))
    checks.append(("README", "PASS" if any((path / name).exists() for name in ("README.md", "README.rst", "README")) else "WARN"))
    checks.append((".gitignore", "PASS" if (path / ".gitignore").exists() else "WARN"))
    checks.append(("Environment template", "PASS" if (path / ".env.example").exists() else "WARN"))
    return checks


@app.command()
def scan(path: Path = typer.Argument(Path("."), exists=True, file_okay=False, dir_okay=True)) -> None:
    """Scan PATH and report basic deployment readiness checks."""
    path = path.resolve()
    console.print(Panel.fit("[bold]ShipCheck[/bold]\nPre-deployment health check"))
    console.print(f"\n[bold]Project:[/bold] {path.name}\n")

    checks = check_project(path)
    for name, status in checks:
        if status == "PASS":
            console.print(f"  [green]✓[/green] {name}")
        elif status == "WARN":
            console.print(f"  [yellow]⚠[/yellow] {name}")
        else:
            console.print(f"  [red]✗[/red] {name}")

    passed = sum(status == "PASS" for _, status in checks)
    score = round((passed / len(checks)) * 100)
    console.print(f"\n[bold]Deployment Readiness:[/bold] {score}%")


if __name__ == "__main__":
    app()
