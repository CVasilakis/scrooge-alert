import logging
from abc import ABC, abstractmethod
from rich.live import Live
from rich.text import Text

class ProgressStrategy(ABC):
    @abstractmethod
    def start(self, total_delay: float) -> None:
        """Starts the progress tracking.

        Args:
            total_delay (float): The total delay in seconds.
        """
        pass

    @abstractmethod
    def display_progress(self, remaining: float) -> None:
        """Displays the progress of a delay/sleep operation.

        Args:
            remaining (float): The remaining time in seconds.
        """
        pass

    @abstractmethod
    def cancel(self) -> bool:
        """Cancels the progress tracking, cleaning up the display.
        
        Returns:
            bool: True if a progress display was active and cancelled, False otherwise.
        """
        pass

    @abstractmethod
    def complete(self, actual_delay: float) -> None:
        """Called when the delay operation is complete.

        Args:
            actual_delay (float): The total actual time slept in seconds.
        """
        pass

class InteractiveProgressStrategy(ProgressStrategy):
    def __init__(self):
        self.live = None
        self.total_delay = 0.0

    def start(self, total_delay: float) -> None:
        """Initializes and starts the live countdown.
        
        Args:
            total_delay (float): The total delay in seconds.
        """
        self.cancel()
        
        self.total_delay = total_delay
        
        # Ensure a blank line before the progress bar for visual spacing
        print()

        self.live = Live(Text(f"⏳ Sleeping for {total_delay:.1f} seconds..."), transient=True, refresh_per_second=10)
        self.live.start()

    def display_progress(self, remaining: float) -> None:
        """Updates the live countdown interactively.

        Args:
            remaining (float): The remaining time in seconds.
        """
        if self.live is not None:
            self.live.update(Text(f"⏳ Sleeping for {remaining:.1f} seconds..."))

    def cancel(self) -> bool:
        """Stops the live display to clean up the terminal line.
        
        Returns:
            bool: True if the live display was active and stopped, False otherwise.
        """
        if self.live is not None:
            self.live.stop()
            self.live = None
            return True
        return False

    def complete(self, actual_delay: float) -> None:
        """Stops the display and logs the completed sleep time.

        Args:
            actual_delay (float): The total actual time slept in seconds.
        """
        self.cancel()
        logging.info(f"⏳ Slept for {actual_delay:.1f} seconds")

class SilentProgressStrategy(ProgressStrategy):
    def start(self, total_delay: float) -> None:
        """A no-op for starting progress silently."""
        pass

    def display_progress(self, remaining: float) -> None:
        """A no-op for displaying progress silently."""
        pass

    def cancel(self) -> bool:
        """A no-op for cancelling progress silently.
        
        Returns:
            bool: Always False.
        """
        return False

    def complete(self, actual_delay: float) -> None:
        """A no-op for completing progress silently."""
        pass
