import logging
from abc import ABC, abstractmethod
from typing import Optional
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from rich.spinner import Spinner
from rich.progress_bar import ProgressBar

class ExecutionStrategy(ABC):
    """Abstract base class for execution UI and logging strategies."""
    @abstractmethod
    def start_target(self, target_name: str, target_logger: logging.Logger) -> None:
        """Called when a new scraping target begins."""
        pass

    @abstractmethod
    def start_scraping(self, name: str) -> None:
        """Called when scraping for a specific product begins."""
        pass

    @abstractmethod
    def complete_scraping(self) -> None:
        """Called when scraping for a specific product ends."""
        pass

    @abstractmethod
    def log_result(self, icon: str, name: str, value: str, note: Optional[str] = None) -> None:
        """Logs a successful or informational result."""
        pass

    @abstractmethod
    def log_warning(self, name: str, warning_str: str, note: Optional[str] = None) -> None:
        """Logs a warning message for a specific product."""
        pass

    @abstractmethod
    def log_error(self, name: str, error_str: str, note: Optional[str] = None) -> None:
        """Logs an error message for a specific product."""
        pass

    @abstractmethod
    def start_sleep(self, total_delay: float) -> None:
        """Called when a sleep/delay period begins."""
        pass

    @abstractmethod
    def update_sleep(self, remaining: float) -> None:
        """Called to update the progress of an ongoing sleep period."""
        pass

    @abstractmethod
    def complete_sleep(self, actual_delay: float) -> None:
        """Called when a sleep/delay period ends."""
        pass

    @abstractmethod
    def complete_target(self) -> None:
        """Called when a scraping target completes its execution."""
        pass

    @abstractmethod
    def log_interrupt(self, message: str) -> None:
        """Logs an interruption or early termination signal."""
        pass


class InteractiveExecutionStrategy(ExecutionStrategy):
    """Execution strategy that updates a rich console live display for interactive usage."""
    def __init__(self):
        """Initializes the interactive strategy state."""
        self.console = Console()
        self.live = None
        self.rows = []
        self.notes = []
        self.target_name = ""
        self.sleep_total = 0.0
        self.sleep_remaining = 0.0
        self.is_sleeping = False
        self.scraping_name = ""

    def start_target(self, target_name: str, target_logger: logging.Logger) -> None:
        """Starts a new live display session for the given target."""
        if self.live:
            self.live.stop()

        self.target_name = target_name
        self.rows = []
        self.notes = []
        self.is_sleeping = False
        self.scraping_name = ""

        self.live = Live(self._generate_panel(), refresh_per_second=10)
        self.live.start()

    def start_scraping(self, name: str) -> None:
        """Starts scraping the specified product and updates the live display."""
        self.scraping_name = self._truncate_name(name)
        if self.live:
            self.live.update(self._generate_panel())

    def complete_scraping(self) -> None:
        """Clears the current scraping product from the live display."""
        self.scraping_name = ""
        if self.live:
            self.live.update(self._generate_panel())

    def _truncate_name(self, name: str, max_len: int = 30) -> str:
        """Truncates a name string to fit within the live display panel."""
        if len(name) > max_len:
            return name[:max_len - 3] + "..."
        return name

    def _get_note_ref(self, note: str) -> str:
        """Adds a footnote and returns its formatted reference string."""
        self.notes.append(note)
        return f" [dim default][{len(self.notes)}][/dim default]"

    def _generate_panel(self) -> Panel:
        """Generates the rich panel to be rendered on the live display."""
        display_table = Table(show_header=False, box=None, padding=(0, 2))
        display_table.add_column("Icon", justify="center")
        display_table.add_column("Name", style="bold")
        display_table.add_column("Value")

        for row in self.rows:
            display_table.add_row(*row)

        if self.is_sleeping:
            grid = Table.grid(padding=(0, 1))
            grid.add_row(
                ProgressBar(total=self.sleep_total, completed=self.sleep_remaining, width=30, style="grey37", complete_style="cyan", finished_style="cyan"),
                f"[cyan]{self.sleep_remaining:.1f}s[/cyan]"
            )
            display_table.add_row("⏳", "Sleeping", grid)
        elif self.scraping_name:
            display_table.add_row(Spinner("dots", style="cyan"), escape(self.scraping_name), "[cyan]Scraping...[/cyan]")

        if self.notes:
            notes_group = [""]
            for i, note in enumerate(self.notes, 1):
                notes_group.append(f"  [{i}] {escape(note)}")
            renderable = Group(display_table, Text.from_markup("\n".join(notes_group), style="dim"))
        else:
            renderable = display_table

        panel_color = "blue"
        for row in self.rows:
            if row[0] in ("❗", "🛑"):
                panel_color = "red"
                break

        return Panel(renderable, title=f"[bold]{self.target_name.capitalize()} Scraping[/bold]", border_style=panel_color, width=75)

    def log_result(self, icon: str, name: str, value: str, note: Optional[str] = None) -> None:
        """Logs a standard result directly into the rich table."""
        ref = self._get_note_ref(note) if note else ""
        self.rows.append((icon, escape(self._truncate_name(name)), f"{value}{ref}"))
        if self.live:
            self.live.update(self._generate_panel())

    def log_warning(self, name: str, warning_str: str, note: Optional[str] = None) -> None:
        """Logs a warning entry to the live display."""
        ref = self._get_note_ref(note) if note else ""
        self.rows.append(("🟡", escape(self._truncate_name(name)), f"[yellow]{escape(warning_str)}{ref}[/yellow]"))
        if self.live:
            self.live.update(self._generate_panel())

    def log_error(self, name: str, error_str: str, note: Optional[str] = None) -> None:
        """Logs an error entry to the live display."""
        ref = self._get_note_ref(note) if note else ""
        self.rows.append(("❗", escape(self._truncate_name(name)), f"{escape(error_str)}{ref}"))
        if self.live:
            self.live.update(self._generate_panel())

    def start_sleep(self, total_delay: float) -> None:
        """Starts the sleep state and renders a progress bar."""
        self.is_sleeping = True
        self.sleep_total = total_delay
        self.sleep_remaining = total_delay
        if self.live:
            self.live.update(self._generate_panel())

    def update_sleep(self, remaining: float) -> None:
        """Updates the progress bar with the remaining sleep duration."""
        self.sleep_remaining = remaining
        if self.live:
            self.live.update(self._generate_panel())

    def complete_sleep(self, actual_delay: float) -> None:
        """Completes the sleep state and removes the progress bar."""
        self.is_sleeping = False
        if self.live:
            self.live.update(self._generate_panel())


    def complete_target(self) -> None:
        """Stops the live display console for the target."""
        if self.live:
            self.live.stop()
            self.live = None
            self.console.print()

    def log_interrupt(self, message: str) -> None:
        """Logs an interruption event."""
        if self.live:
            self.is_sleeping = False
            self.scraping_name = ""
            self.rows.append(("🛑", "Interrupted", escape(message)))
            self.live.update(self._generate_panel())
        else:
            logging.info(f"🛑 {message}", extra={"pad_top": 1, "pad_bottom": 1})


class SilentExecutionStrategy(ExecutionStrategy):
    """Execution strategy that operates without an active rich live UI, logging purely to a target logger."""
    def __init__(self):
        """Initializes the silent strategy execution."""
        self.target_logger = None

    def start_target(self, target_name: str, target_logger: logging.Logger) -> None:
        """Sets the underlying logger context to use for output."""
        self.target_logger = target_logger

    def start_scraping(self, name: str) -> None:
        """Does nothing in silent mode."""
        pass

    def complete_scraping(self) -> None:
        """Does nothing in silent mode."""
        pass

    def log_result(self, icon: str, name: str, value: str, note: Optional[str] = None) -> None:
        """Logs an informational result to the target logger."""
        if self.target_logger:
            clean_value = value.replace('[green]', '').replace('[/green]', '').replace('[red]', '').replace('[/red]', '')
            if note:
                self.target_logger.info(f"{icon} {name}: {clean_value} ({note})")
            else:
                self.target_logger.info(f"{icon} {name}: {clean_value}")

    def log_warning(self, name: str, warning_str: str, note: Optional[str] = None) -> None:
        """Logs a warning to the target logger."""
        if self.target_logger:
            if note:
                self.target_logger.warning(f"❗ {name}: {warning_str} ({note})")
            else:
                self.target_logger.warning(f"❗ {name}: {warning_str}")

    def log_error(self, name: str, error_str: str, note: Optional[str] = None) -> None:
        """Logs an error to the target logger."""
        if self.target_logger:
            if note:
                self.target_logger.error(f"❗ {name}: {error_str} ({note})")
            else:
                self.target_logger.error(f"❗ {name}: {error_str}")

    def start_sleep(self, total_delay: float) -> None:
        """Does nothing in silent mode."""
        pass

    def update_sleep(self, remaining: float) -> None:
        """Does nothing in silent mode."""
        pass

    def complete_sleep(self, actual_delay: float) -> None:
        """Does nothing in silent mode."""
        pass


    def complete_target(self) -> None:
        """Clears the target logger context."""
        self.target_logger = None

    def log_interrupt(self, message: str) -> None:
        """Logs an interrupt message to the target logger or root logger."""
        if self.target_logger:
            self.target_logger.info(f"🛑 {message}")
        else:
            logging.info(f"🛑 {message}")
