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
    @abstractmethod
    def start_target(self, target_name: str, target_logger: logging.Logger) -> None:
        pass

    @abstractmethod
    def start_scraping(self, name: str) -> None:
        pass

    @abstractmethod
    def complete_scraping(self) -> None:
        pass

    @abstractmethod
    def log_result(self, icon: str, name: str, value: str, note: Optional[str] = None) -> None:
        pass

    @abstractmethod
    def log_warning(self, name: str, warning_str: str, note: Optional[str] = None) -> None:
        pass

    @abstractmethod
    def log_error(self, name: str, error_str: str, note: Optional[str] = None) -> None:
        pass

    @abstractmethod
    def start_sleep(self, total_delay: float) -> None:
        pass

    @abstractmethod
    def update_sleep(self, remaining: float) -> None:
        pass

    @abstractmethod
    def complete_sleep(self, actual_delay: float) -> None:
        pass

    @abstractmethod
    def cancel_sleep(self) -> bool:
        pass

    @abstractmethod
    def complete_target(self) -> None:
        pass


class InteractiveExecutionStrategy(ExecutionStrategy):
    def __init__(self):
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
        self.scraping_name = self._truncate_name(name)
        if self.live:
            self.live.update(self._generate_panel())

    def complete_scraping(self) -> None:
        self.scraping_name = ""
        if self.live:
            self.live.update(self._generate_panel())

    def _truncate_name(self, name: str, max_len: int = 30) -> str:
        if len(name) > max_len:
            return name[:max_len - 3] + "..."
        return name

    def _get_note_ref(self, note: str) -> str:
        self.notes.append(note)
        return f" [dim default][{len(self.notes)}][/dim default]"

    def _generate_panel(self) -> Panel:
        display_table = Table(show_header=False, box=None, padding=(0, 2))
        display_table.add_column("Icon", justify="center")
        display_table.add_column("Name", style="bold")
        display_table.add_column("Value")

        for row in self.rows:
            display_table.add_row(*row)

        if self.is_sleeping:
            grid = Table.grid(padding=(0, 1))
            grid.add_row(
                ProgressBar(total=self.sleep_total, completed=self.sleep_remaining, width=30, style="grey37", complete_style="cyan"),
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

        return Panel(renderable, title=f"[bold]{self.target_name.capitalize()} Scraping[/bold]", border_style="magenta", width=75)

    def log_result(self, icon: str, name: str, value: str, note: Optional[str] = None) -> None:
        ref = self._get_note_ref(note) if note else ""
        self.rows.append((icon, escape(self._truncate_name(name)), f"{value}{ref}"))
        if self.live:
            self.live.update(self._generate_panel())

    def log_warning(self, name: str, warning_str: str, note: Optional[str] = None) -> None:
        ref = self._get_note_ref(note) if note else ""
        self.rows.append(("🟡", escape(self._truncate_name(name)), f"[yellow]{escape(warning_str)}{ref}[/yellow]"))
        if self.live:
            self.live.update(self._generate_panel())

    def log_error(self, name: str, error_str: str, note: Optional[str] = None) -> None:
        ref = self._get_note_ref(note) if note else ""
        self.rows.append(("❗", escape(self._truncate_name(name)), f"[red]{escape(error_str)}{ref}[/red]"))
        if self.live:
            self.live.update(self._generate_panel())

    def start_sleep(self, total_delay: float) -> None:
        self.is_sleeping = True
        self.sleep_total = total_delay
        self.sleep_remaining = total_delay
        if self.live:
            self.live.update(self._generate_panel())

    def update_sleep(self, remaining: float) -> None:
        self.sleep_remaining = remaining
        if self.live:
            self.live.update(self._generate_panel())

    def complete_sleep(self, actual_delay: float) -> None:
        self.is_sleeping = False
        if self.live:
            self.live.update(self._generate_panel())

    def cancel_sleep(self) -> bool:
        if self.is_sleeping:
            self.is_sleeping = False
            if self.live:
                self.live.update(self._generate_panel())
            return True
        return False

    def complete_target(self) -> None:
        if self.live:
            self.live.stop()
            self.live = None
            self.console.print()


class SilentExecutionStrategy(ExecutionStrategy):
    def __init__(self):
        self.target_logger = None

    def start_target(self, target_name: str, target_logger: logging.Logger) -> None:
        self.target_logger = target_logger

    def start_scraping(self, name: str) -> None:
        pass

    def complete_scraping(self) -> None:
        pass

    def log_result(self, icon: str, name: str, value: str, note: Optional[str] = None) -> None:
        if self.target_logger:
            clean_value = value.replace('[green]', '').replace('[/green]', '').replace('[red]', '').replace('[/red]', '')
            if note:
                self.target_logger.info(f"{icon} {name}: {clean_value} ({note})")
            else:
                self.target_logger.info(f"{icon} {name}: {clean_value}")

    def log_warning(self, name: str, warning_str: str, note: Optional[str] = None) -> None:
        if self.target_logger:
            if note:
                self.target_logger.warning(f"❗ {name}: {warning_str} ({note})")
            else:
                self.target_logger.warning(f"❗ {name}: {warning_str}")

    def log_error(self, name: str, error_str: str, note: Optional[str] = None) -> None:
        if self.target_logger:
            if note:
                self.target_logger.error(f"❗ {name}: {error_str} ({note})")
            else:
                self.target_logger.error(f"❗ {name}: {error_str}")

    def start_sleep(self, total_delay: float) -> None:
        pass

    def update_sleep(self, remaining: float) -> None:
        pass

    def complete_sleep(self, actual_delay: float) -> None:
        pass

    def cancel_sleep(self) -> bool:
        return False

    def complete_target(self) -> None:
        self.target_logger = None
