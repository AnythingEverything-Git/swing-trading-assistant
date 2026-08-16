"""Application-level scan orchestrator signatures.

These are use-case signatures only; no business logic is implemented.
"""
from typing import Protocol, Dict, Any


class ScanOrchestrator(Protocol):
    """Protocol for a scan orchestrator use-case.

    Implementations should coordinate the universe fetch, analysis via a Strategy,
    and return a domain `ScanRun` instance. Types are intentionally referenced
    in documentation to avoid hard imports at this stage.
    """

    def run_scan(self, provider: object, strategy: object, params: Dict[str, Any]) -> object:  # pragma: no cover - interface
        ...
