"""Schema migrations for the static quote-image vertical.

Applied lazily by db.connect() so every caller sees the same schema no matter
which db.py function it reaches first. The re-exports keep db.py's import
simple while the numbered file stays importable via importlib.
"""

from importlib import import_module

_migration = import_module(__name__ + ".001_add_vertical")

VERSION = _migration.VERSION
migrate = _migration.migrate
current_version = _migration.current_version

__all__ = ["VERSION", "migrate", "current_version"]
