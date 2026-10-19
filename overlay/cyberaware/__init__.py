"""CyberAware defense controls for AIGoat.

Installed into ``app/defense/controls/cyberaware/`` by ``scripts/install-overlay.sh``.
AIGoat's ``app/defense/controls/__init__.py`` calls ``register_cyberaware_controls``
from ``ensure_registered`` (patches/0001-register-cyberaware.patch), so profile
YAML can name these control ids.
"""
from __future__ import annotations

from typing import Callable

from .trust_gate import TrustGateControl

__all__ = ["TrustGateControl", "register_cyberaware_controls"]


def register_cyberaware_controls(register_if_missing: Callable[[object], None]) -> None:
    """Register every CyberAware control with AIGoat's idempotent registrar."""
    register_if_missing(TrustGateControl())
