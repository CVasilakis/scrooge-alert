import os
import sys
import apprise

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env import check_env_file, APPRISE_PLACEHOLDERS
from notifier import Notifier
from logger import setup_global_logging
from exceptions import EnvFileError

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape

def obfuscate_invalid_url(url: str) -> str:
    """Obfuscates an invalid URL for display."""
    schema_end = url.find('://')
    if schema_end != -1:
        scheme = url[:schema_end + 3]
        rest = url[schema_end + 3:]
    else:
        scheme = ""
        rest = url

    first_slash = rest.find('/')
    if first_slash != -1:
        token = rest[:first_slash]
        path = '/...'
    else:
        token = rest
        path = ''

    if len(token) > 2:
        obfuscated_token = f"{token[0]}...{token[-1]}"
    elif len(token) > 0:
        obfuscated_token = f"{token[0]}..."
    else:
        obfuscated_token = ""

    if not scheme and not obfuscated_token:
        return "***"
    return f"{scheme}{obfuscated_token}{path}"

def main():
    """Main entry point for sending a test notification.

    This function initializes the notifier with URLs from the environment and sends
    a test message, reporting the success or failure of each configured service using rich UI.
    """
    setup_global_logging()
    console = Console()
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Icon", justify="center")
    table.add_column("Status", style="bold")
    table.add_column("Endpoint")

    notes = []
    def get_note_ref(note: str) -> str:
        notes.append(note)
        return f" [dim default][{len(notes)}][/dim default]"

    env_error_msg = ""
    try:
        check_env_file()
    except EnvFileError as e:
        env_error_msg = str(e)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    valid_urls = []
    invalid_urls = []

    if notification_urls:
        for u in notification_urls.split(','):
            u = u.strip()
            if u:
                if not any(p in u for p in APPRISE_PLACEHOLDERS) and apprise.Apprise.instantiate(u):
                    valid_urls.append(u)
                else:
                    invalid_urls.append(u)

    for iu in invalid_urls:
        ref = get_note_ref("Apprise could not instantiate this endpoint.")
        table.add_row("❗", "Invalid URL", f"[yellow]{escape(obfuscate_invalid_url(iu))}{ref}[/yellow]")

    if valid_urls:
        notifier = Notifier(",".join(valid_urls))
        with console.status("[bold green]Sending test messages...[/bold green]", spinner="dots"):
            results = notifier.notify_test()

        for identifier, success in results:
            if success:
                table.add_row("✅", "Success", f"[green]{escape(identifier)}[/green]")
            else:
                ref = get_note_ref("Failed to deliver the test message.")
                table.add_row("🛑", "Delivery Failed", f"[red]{escape(identifier)}{ref}[/red]")

    if not valid_urls and not invalid_urls:
        table.add_row("🛑", "Not Configured", f"[red]{env_error_msg or 'No notification URLs found.'}[/red]")

    if notes:
        notes_group = [""]
        for i, note in enumerate(notes, 1):
            notes_group.append(f"  [{i}] {escape(note)}")
        console.print(Panel(Group(table, Text.from_markup("\n".join(notes_group), style="dim")), title="[bold]Test Notification[/bold]", border_style="blue", width=75))
    else:
        console.print(Panel(table, title="[bold]Test Notification[/bold]", border_style="blue", width=75))

    console.print()

if __name__ == "__main__":
    main()
