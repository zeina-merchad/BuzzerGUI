"""
timer.py — public re-export of CountdownTimer
==============================================

The canonical implementation lives inside engine.py so that the engine module
is fully self-contained and can be unit-tested without importing this file.

This module previously contained a near-identical duplicate class.  Having two
separate CountdownTimer definitions caused subtle divergence over time (e.g.
the stop() / changed(0) emission fix was applied to engine.CountdownTimer but
not to this copy — the duplicate here still called self._timer.start() inside
start() without stopping first, so a rapid re-unlock could stack two concurrent
QTimer fires and produce double tick-rate countdowns).

Any external code that does ``from app.core.timer import CountdownTimer`` now
gets the single source-of-truth implementation.
"""
from app.core.engine import CountdownTimer  # noqa: F401  re-exported for callers

__all__ = ["CountdownTimer"]