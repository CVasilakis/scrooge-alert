import logging
from abc import ABC, abstractmethod

class ProgressStrategy(ABC):
    @abstractmethod
    def display_progress(self, remaining: float) -> None:
        """Displays the progress of a delay/sleep operation.
        
        Args:
            remaining (float): The remaining time in seconds.
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
    def display_progress(self, remaining: float) -> None:
        """Prints the remaining sleep time to the console interactively.
        
        Args:
            remaining (float): The remaining time in seconds.
        """
        print(f"\r⏳ Sleeping for {remaining:.1f} seconds...   ", end="", flush=True)

    def complete(self, actual_delay: float) -> None:
        """Clears the progress line and logs the completed sleep time.
        
        Args:
            actual_delay (float): The total actual time slept in seconds.
        """
        print("\r" + " " * 40 + "\r", end="", flush=True)
        logging.info(f"⏳ Slept for {actual_delay:.1f} seconds.")

class SilentProgressStrategy(ProgressStrategy):
    def display_progress(self, remaining: float) -> None:
        """A no-op for displaying progress silently.
        
        Args:
            remaining (float): The remaining time in seconds (ignored).
        """
        pass

    def complete(self, actual_delay: float) -> None:
        """A no-op for completing progress silently.
        
        Args:
            actual_delay (float): The total actual time slept in seconds (ignored).
        """
        pass
