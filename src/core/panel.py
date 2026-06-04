from typing import Optional, List
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape


class StatusPanelBuilder:
    """Reusable builder for Rich status panels with icon-based rows, footnotes, and automatic border coloring.

    Encapsulates the repeated pattern of: 3-column table (icon, label, value) +
    footnotes + icon-driven border color. Used by CLI tools (main, status, ping)
    to render consistent, self-contained status panels.

    Usage:
        panel = StatusPanelBuilder("My Panel Title")
        ref = panel.add_note_ref("Some footnote text")
        panel.add_row("✅", "Label", f"Value{ref}")
        panel.render(console)
    """

    def __init__(self, title: str, width: int = 75):
        """Initializes the panel builder.

        Args:
            title (str): The panel title displayed in the border.
            width (int): The panel width in characters. Defaults to 75.
        """
        self.title = title
        self.width = width
        self.table = Table(show_header=False, box=None, padding=(0, 2))
        self.table.add_column("Icon", justify="center")
        self.table.add_column("Label", style="bold")
        self.table.add_column("Value")
        self.notes: List[str] = []
        self.icons: List[str] = []

    def add_row(self, icon: str, label: str, value: str) -> None:
        """Adds a row to the panel and tracks the icon for border color calculation.

        Args:
            icon (str): The status icon (e.g., '✅', '🟡', '❗', '🛑').
            label (str): The row label (rendered bold).
            value (str): The row value (supports Rich markup).
        """
        self.icons.append(icon)
        self.table.add_row(icon, label, value)

    def add_note_ref(self, note: str) -> str:
        """Adds a footnote and returns its formatted reference markup.

        The reference is a dim, bracketed number (e.g., '[1]') that can be
        appended to a row's value to link it to the footnote.

        Args:
            note (str): The footnote text.

        Returns:
            str: The Rich markup string for the footnote reference.
        """
        self.notes.append(note)
        return f" [dim default][{len(self.notes)}][/dim default]"

    def get_panel_color(self) -> str:
        """Determines the panel border color based on the tracked icons.

        Priority: red (if any '❗') > yellow (if any '🟡') > green (default).

        Returns:
            str: The Rich color string for the panel border.
        """
        if "❗" in self.icons:
            return "red"
        elif "🟡" in self.icons:
            return "yellow"
        return "green"

    def render(self, console: Console, panel_color: Optional[str] = None) -> None:
        """Renders the panel to the given console.

        Args:
            console (Console): The Rich console to print to.
            panel_color (Optional[str]): Override for the border color.
                If None, the color is determined automatically by get_panel_color().
        """
        color = panel_color or self.get_panel_color()

        if self.notes:
            notes_lines = [""]
            for i, note in enumerate(self.notes, 1):
                notes_lines.append(f"  [{i}] {escape(note)}")
            renderable = Group(self.table, Text.from_markup("\n".join(notes_lines), style="dim"))
        else:
            renderable = self.table

        console.print(Panel(renderable, title=f"[bold]{self.title}[/bold]", border_style=color, width=self.width))
