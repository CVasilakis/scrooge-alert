import logging
from abc import ABC, abstractmethod

class ProgressStrategy(ABC):
    @abstractmethod
    def display_progress(self, remaining: float) -> None:
        pass

    @abstractmethod
    def complete(self, actual_delay: float) -> None:
        pass

class InteractiveProgressStrategy(ProgressStrategy):
    def display_progress(self, remaining: float) -> None:
        print(f"\r⏳ Sleeping for {remaining:.1f} seconds...   ", end="", flush=True)

    def complete(self, actual_delay: float) -> None:
        print("\r" + " " * 40 + "\r", end="", flush=True)
        logging.info(f"⏳ Slept for {actual_delay:.1f} seconds.")

class SilentProgressStrategy(ProgressStrategy):
    def display_progress(self, remaining: float) -> None:
        pass

    def complete(self, actual_delay: float) -> None:
        pass
