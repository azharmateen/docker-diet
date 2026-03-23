"""Textual TUI dashboard for Docker resource management."""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Static, Tree, Label, Button,
    ProgressBar, DataTable, RichLog,
)
from textual.binding import Binding
from textual import work
from rich.text import Text

from .scanner import full_scan, ScanResult
from .analyzer import analyze, AnalysisResult, group_images_by_repo, format_size
from .cleaner import plan_cleanup, execute_cleanup, quick_clean


class SizeBar(Static):
    """Visual size bar widget."""

    def __init__(self, label: str, size: int, max_size: int, color: str = "green"):
        super().__init__()
        self.bar_label = label
        self.size = size
        self.max_size = max_size
        self.color = color

    def render(self) -> Text:
        width = 30
        ratio = self.size / self.max_size if self.max_size > 0 else 0
        filled = int(ratio * width)
        bar = "\u2588" * filled + "\u2591" * (width - filled)
        return Text.from_markup(
            f"  {self.bar_label:<20} [{self.color}]{bar}[/] {format_size(self.size)}"
        )


class DockerDietApp(App):
    """Docker Diet TUI Application."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;
        grid-rows: 1fr 3fr;
        grid-columns: 1fr 1fr;
    }
    #summary {
        column-span: 2;
        border: solid $accent;
        padding: 1;
    }
    #resources {
        border: solid $primary;
        padding: 1;
        height: 100%;
    }
    #details {
        border: solid $secondary;
        padding: 1;
        height: 100%;
    }
    .section-title {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }
    .reclaimable {
        color: $warning;
        text-style: bold;
    }
    #action-buttons {
        dock: bottom;
        height: 3;
        layout: horizontal;
    }
    #action-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("c", "clean", "Quick Clean"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.scan_result: ScanResult | None = None
        self.analysis: AnalysisResult | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="summary"):
            yield Label("[bold]Docker Diet[/bold] - Scanning...", id="summary-label")
            yield Static("", id="size-bars")

        with ScrollableContainer(id="resources"):
            yield Label("[bold]Resources[/bold]", classes="section-title")
            yield Tree("Docker Resources", id="resource-tree")

        with Vertical(id="details"):
            yield Label("[bold]Details[/bold]", classes="section-title")
            yield DataTable(id="detail-table")
            with Horizontal(id="action-buttons"):
                yield Button("Refresh", id="btn-refresh", variant="primary")
                yield Button("Quick Clean", id="btn-clean", variant="warning")

        yield Footer()

    def on_mount(self) -> None:
        self.do_scan()

    @work(thread=True)
    def do_scan(self) -> None:
        """Scan Docker resources in background thread."""
        self.scan_result = full_scan()
        if self.scan_result.error:
            self.call_from_thread(self._show_error, self.scan_result.error)
            return
        self.analysis = analyze(self.scan_result)
        self.call_from_thread(self._update_ui)

    def _show_error(self, error: str) -> None:
        label = self.query_one("#summary-label", Label)
        label.update(f"[red]Error: {error}[/red]")

    def _update_ui(self) -> None:
        if not self.scan_result or not self.analysis:
            return

        scan = self.scan_result
        analysis = self.analysis

        # Update summary
        label = self.query_one("#summary-label", Label)
        label.update(
            f"[bold]Docker Diet[/bold] | "
            f"Images: {len(scan.images)} | "
            f"Containers: {len(scan.containers)} | "
            f"Volumes: {len(scan.volumes)} | "
            f"Total: [cyan]{format_size(scan.total_size)}[/cyan] | "
            f"Reclaimable: [yellow]{format_size(analysis.total_reclaimable)}[/yellow]"
        )

        # Update size bars
        max_size = max(scan.total_image_size, scan.total_container_size,
                       scan.total_volume_size, scan.total_cache_size, 1)
        bars_widget = self.query_one("#size-bars", Static)
        bars_text = Text()
        for label_text, size, color in [
            ("Images", scan.total_image_size, "cyan"),
            ("Containers", scan.total_container_size, "green"),
            ("Volumes", scan.total_volume_size, "yellow"),
            ("Build Cache", scan.total_cache_size, "magenta"),
        ]:
            ratio = size / max_size if max_size > 0 else 0
            filled = int(ratio * 25)
            bar = "\u2588" * filled + "\u2591" * (25 - filled)
            bars_text.append(f"  {label_text:<15} ")
            bars_text.append(bar, style=color)
            bars_text.append(f" {format_size(size)}\n")
        bars_widget.update(bars_text)

        # Update resource tree
        tree = self.query_one("#resource-tree", Tree)
        tree.clear()

        # Images
        img_node = tree.root.add(
            f"Images ({len(scan.images)}) - {format_size(scan.total_image_size)}"
        )
        groups = group_images_by_repo(scan.images)
        for repo, images in groups.items():
            repo_size = sum(i.size for i in images)
            repo_node = img_node.add(f"{repo} ({len(images)}) - {format_size(repo_size)}")
            for img in images:
                style = "red" if img.dangling else "white"
                repo_node.add_leaf(
                    f"[{style}]{img.tag} - {format_size(img.size)}[/{style}]"
                )

        # Containers
        cont_node = tree.root.add(f"Containers ({len(scan.containers)})")
        running = [c for c in scan.containers if c.is_running]
        stopped = [c for c in scan.containers if not c.is_running]

        if running:
            run_node = cont_node.add(f"Running ({len(running)})")
            for c in running:
                run_node.add_leaf(f"[green]{c.name}[/green] ({c.image})")

        if stopped:
            stop_node = cont_node.add(f"Stopped ({len(stopped)})")
            for c in stopped:
                stop_node.add_leaf(
                    f"[red]{c.name}[/red] ({c.image}) - {c.status}"
                )

        # Volumes
        vol_node = tree.root.add(f"Volumes ({len(scan.volumes)})")
        for v in scan.volumes:
            status = "[green]in use[/green]" if v.in_use else "[yellow]unused[/yellow]"
            vol_node.add_leaf(f"{v.name[:40]} {status}")

        # Reclaimable
        reclaim_node = tree.root.add(
            f"[bold yellow]Reclaimable: {format_size(analysis.total_reclaimable)}[/bold yellow]"
        )
        for cat in analysis.categories:
            if cat.count > 0:
                reclaim_node.add_leaf(
                    f"{cat.name}: {cat.count} item(s) - {format_size(cat.reclaimable_bytes)}"
                )

        tree.root.expand_all()

        # Update detail table
        table = self.query_one("#detail-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Category", "Count", "Size", "Reclaimable")
        table.add_row("Images", str(len(scan.images)),
                       format_size(scan.total_image_size),
                       format_size(analysis.dangling_images.reclaimable_bytes))
        table.add_row("Containers", str(len(scan.containers)),
                       format_size(scan.total_container_size),
                       format_size(analysis.stopped_containers.reclaimable_bytes))
        table.add_row("Volumes", str(len(scan.volumes)),
                       format_size(scan.total_volume_size),
                       format_size(analysis.unused_volumes.reclaimable_bytes))
        table.add_row("Build Cache", str(len(scan.build_cache)),
                       format_size(scan.total_cache_size),
                       format_size(analysis.build_cache.reclaimable_bytes))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            self.action_refresh()
        elif event.button.id == "btn-clean":
            self.action_clean()

    def action_refresh(self) -> None:
        label = self.query_one("#summary-label", Label)
        label.update("[bold]Docker Diet[/bold] - Scanning...")
        self.do_scan()

    @work(thread=True)
    def action_clean(self) -> None:
        result = quick_clean()
        self.call_from_thread(self._after_clean, result.summary)

    def _after_clean(self, summary: str) -> None:
        label = self.query_one("#summary-label", Label)
        label.update(f"[bold]Docker Diet[/bold] - {summary}")
        self.do_scan()


def run_dashboard():
    """Launch the TUI dashboard."""
    app = DockerDietApp()
    app.run()
