"""CLI for docker-diet: Docker disk usage visualizer and cleaner."""

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .scanner import full_scan
from .analyzer import analyze, format_size
from .cleaner import plan_cleanup, execute_cleanup, quick_clean
from .reporter import terminal_report, json_report, markdown_report

console = Console()


@click.group()
def cli():
    """docker-diet: Visualize Docker disk usage and safely clean up resources."""
    pass


@cli.command()
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--old-days", default=7, help="Flag containers stopped for N+ days")
def scan(json_output, old_days):
    """Scan Docker resources and show disk usage."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Scanning Docker resources...", total=None)
        result = full_scan()

    if result.error:
        console.print(f"[red]Error: {result.error}[/red]")
        sys.exit(1)

    analysis = analyze(result, old_days=old_days)

    if json_output:
        click.echo(json.dumps(json_report(result, analysis), indent=2))
    else:
        console.print(terminal_report(result, analysis))


@cli.command()
@click.option("--dangling/--no-dangling", default=True, help="Remove dangling images")
@click.option("--stopped/--no-stopped", default=False, help="Remove stopped containers")
@click.option("--volumes/--no-volumes", default=False, help="Remove unused volumes")
@click.option("--cache/--no-cache", default=False, help="Remove build cache")
@click.option("--old-days", default=None, type=int, help="Only remove containers older than N days")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def clean(dangling, stopped, volumes, cache, old_days, dry_run, force):
    """Safely clean up Docker resources."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Scanning...", total=None)
        scan_result = full_scan()

    if scan_result.error:
        console.print(f"[red]Error: {scan_result.error}[/red]")
        sys.exit(1)

    analysis = analyze(scan_result, old_days=old_days or 7)

    actions = plan_cleanup(
        analysis,
        remove_dangling=dangling,
        remove_stopped=stopped,
        remove_volumes=volumes,
        remove_cache=cache,
        old_days=old_days,
    )

    if not actions:
        console.print("[green]Nothing to clean up![/green]")
        return

    # Show plan
    table = Table(title="Cleanup Plan")
    table.add_column("Type", style="cyan")
    table.add_column("Resource")
    table.add_column("Size", justify="right")

    total_size = 0
    for action in actions:
        table.add_row(action.resource_type, action.description, format_size(action.size))
        total_size += action.size

    table.add_row("", "[bold]Total[/bold]", f"[bold]{format_size(total_size)}[/bold]")
    console.print(table)

    if dry_run:
        console.print(f"\n[yellow]DRY RUN: Would remove {len(actions)} resource(s)[/yellow]")
        return

    if not force:
        if not click.confirm(f"\nRemove {len(actions)} resource(s)?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Execute
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Cleaning up...", total=None)
        cleanup_result = execute_cleanup(actions)

    # Report
    for action in cleanup_result.actions:
        if action.success:
            console.print(f"  [green]Removed[/green] {action.description}")
        else:
            console.print(f"  [red]Failed[/red] {action.description}: {action.error}")

    console.print(f"\n{cleanup_result.summary}")


@cli.command()
def dashboard():
    """Launch interactive TUI dashboard."""
    from .app import run_dashboard
    run_dashboard()


@cli.command()
@click.option("--format", "-f", "fmt", default="terminal",
              type=click.Choice(["terminal", "json", "markdown"]),
              help="Report format")
@click.option("--output", "-o", default=None, help="Output file")
def report(fmt, output):
    """Generate a Docker resource report."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Scanning...", total=None)
        scan_result = full_scan()

    if scan_result.error:
        console.print(f"[red]Error: {scan_result.error}[/red]")
        sys.exit(1)

    analysis = analyze(scan_result)

    if fmt == "json":
        text = json.dumps(json_report(scan_result, analysis), indent=2)
    elif fmt == "markdown":
        text = markdown_report(scan_result, analysis)
    else:
        text = terminal_report(scan_result, analysis)

    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"[green]Report written to {output}[/green]")
    else:
        click.echo(text)


if __name__ == "__main__":
    cli()
