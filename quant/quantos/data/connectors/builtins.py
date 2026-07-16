"""Registry of built-in connectors.

Each built-in connector is imported here so it self-registers on package import.
This is the ONE place that lists built-ins; adding a *third-party* connector
needs no edit here — importing its module (which uses ``@register``) is enough.
"""

from __future__ import annotations

# Built-in connectors are added milestone by milestone. Importing a module runs
# its @register decorator. WP-2.4 adds `market`; WP-2.5 adds derivatives,
# onchain, macro, sentiment and news.
BUILTIN_MODULES: tuple[str, ...] = ()
