========
Overview
========

Sygaldry builds objects from configuration files. The process is deterministic
and safe: no ``eval`` is used and resolution always happens bottom-up.

Pipeline
========

#. **Load** a YAML or TOML file.
#. **Include** additional configs via ``_include`` (deep-merge).
#. **Interpolate** ``${...}`` placeholders using environment variables or config paths.
#. **Resolve** component definitions into live objects.

Core Concepts
=============

Component definition
  A mapping is treated as a component definition when it contains ``_type`` or
  ``_func``. A ``_type`` mapping instantiates a class; a ``_func`` mapping
  returns a callable without invoking it.

References
  A mapping of the form ``{_ref: "target"}`` points at another top-level entry
  or a dotted attribute on that entry.

Determinism
  Nested values are resolved depth-first. Child components are instantiated
  before their parents.

Safety
  Imports are done by dotted path. No arbitrary code execution is performed.

Static type checking
  Before resolving, you can run ``sygaldry check`` to generate equivalent
  Python source and pass it to a type checker (``ty``, ``basedpyright``,
  ``pyright``, or ``mypy``). This catches wrong argument names, wrong argument
  types, and ``_ref`` type mismatches without instantiating anything. See
  :doc:`type-checking` for details.
