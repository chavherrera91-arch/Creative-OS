"""Execution layer — interfaces only. Live trading is HARD-DISABLED.

The Broker, RiskGate and ExecutionEngine contracts live here so the rest of the
platform can be written against them today, while real order routing stays off
until it is explicitly, deliberately enabled in a later phase.
"""

from quantos.execution.interfaces import (
    Broker,
    ExecutionEngine,
    LiveExecutionDisabled,
    RiskGate,
    build_execution_engine,
)

__all__ = [
    "Broker",
    "ExecutionEngine",
    "LiveExecutionDisabled",
    "RiskGate",
    "build_execution_engine",
]
