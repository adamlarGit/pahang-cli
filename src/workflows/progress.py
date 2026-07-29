"""Modular Deep Module for standardizing quantity-based progress reporting across all workflows.

Provides a clean, deep interface that encapsulates quantity progress formatting [current/total],
counter tracking, and sink emission, eliminating percentage-based progress across all workflows.
"""

from __future__ import annotations

from typing import Callable, Any

# ProgressSink callback definition: accepts a progress message string
ProgressSink = Callable[..., None]


def format_quantity_progress(current: int, total: int, message: str) -> str:
    """Format quantity progress into the standardized format: [current/total] message."""
    safe_total = max(1, total)
    safe_current = max(0, min(current, safe_total))
    return f"[{safe_current}/{safe_total}] {message}"


class QuantityProgressTracker:
    """Deep module for standardizing quantity-based workflow progress tracking.

    Replaces percentage-based progress ([PROGRESS] 0.0% / 100.0%) with exact quantity progress [current/total].

    Usage:
        tracker = QuantityProgressTracker(total=len(items), sink=progress_sink)
        for idx, item in enumerate(items):
            tracker.emit(idx + 1, f"Processing {item}...")

        tracker.complete("Workflow completed.")
    """

    def __init__(self, total: int = 1, sink: ProgressSink | None = None) -> None:
        self.total = max(1, total)
        self.current = 0
        self.sink = sink

    def set_total(self, total: int) -> None:
        """Dynamically update total quantity if needed."""
        self.total = max(1, total)

    def emit(self, current: int, message: str) -> str:
        """Emit progress for a specific 1-indexed item number."""
        self.current = max(0, min(current, self.total))
        formatted = format_quantity_progress(self.current, self.total, message)
        if self.sink is not None and callable(self.sink):
            self.sink(formatted)
        return formatted

    def advance(self, message: str) -> str:
        """Advance current item index by 1 and emit."""
        return self.emit(self.current + 1, message)

    def complete(self, message: str = "Completed.") -> str:
        """Mark workflow complete [total/total] and emit."""
        return self.emit(self.total, message)

    def notify(self, message: str) -> None:
        """Emit a contextual notification using the current progress index."""
        formatted = format_quantity_progress(self.current if self.current > 0 else 1, self.total, message)
        if self.sink is not None and callable(self.sink):
            self.sink(formatted)
