======================
Command-line interface
======================

Sygaldry ships a ``sygaldry`` CLI for loading config, building objects, and
calling methods directly from the terminal. It is built on Click with
Rich-styled help output.

Commands
========

``sygaldry run``
  Load config, resolve an object, and call it.

``sygaldry show``
  Display the merged config for debugging.

``sygaldry validate``
  Validate config without executing anything.

``sygaldry check``
  Static type check a config file.

``sygaldry interactive``
  Start an interactive Python session with the config loaded.

run
===

.. code-block:: text

   sygaldry run -c CONFIG OBJECT [--set K=V] [--use K=K]
                [--method NAME] [--dry-run] [-v] [-q] [-- ARG ...]

Arguments
---------

``OBJECT`` *(required)*
  Top-level config key to resolve and use.

Options
-------

``-c`` / ``--config`` *(required, repeatable)*
  Path to a YAML or TOML config file. When repeated, files are deep-merged
  left to right so later files override earlier ones.

  Can also be set via the ``SYGALDRY_CONFIG`` environment variable.

``--set`` *(repeatable)*
  Override a config value before interpolation: ``dotted.path=value``.
  Values are automatically coerced (``42`` becomes an int, ``true`` a bool,
  ``null`` becomes ``None``).

``--use`` *(repeatable)*
  Copy a value from one config path to another before interpolation:
  ``target.path=source.path``. Useful for swapping defaults.

``--method``
  Method to call on the resolved object. If omitted, the object itself is
  called (``__call__``). Can also be set via ``_call`` in config.

``--dry-run``
  Validate config and display what would be called, without executing.

``-v`` / ``--verbose``
  Show full tracebacks on error.

``-q`` / ``--quiet``
  Suppress non-error output.

``-- ARG ...``
  Positional arguments passed to the called method, separated from options
  by ``--``. Values are type-coerced the same way as ``--set``.

Return value handling
---------------------

* If the method returns an ``int``, it becomes the process exit code.
* If the method returns a non-``None``, non-``int`` value, it is printed to
  stdout (unless ``-q``).

Examples
--------

.. code-block:: bash

   # Basic: resolve an object and call it
   sygaldry run -c config.yaml pipeline

   # Multiple configs, deep-merged left to right
   sygaldry run -c base.yaml -c prod.yaml pipeline

   # Override a nested value
   sygaldry run -c config.yaml pipeline --set db.host=prod-db

   # Swap a value for another config path
   sygaldry run -c config.yaml pipeline --use db.host=defaults.prod_host

   # Call a specific method with arguments
   sygaldry run -c config.yaml pipeline --method process -- 42 hello true

   # Dry run
   sygaldry run -c config.yaml pipeline --dry-run

show
====

.. code-block:: text

   sygaldry show -c CONFIG [--set K=V] [--use K=K] [--object KEY]
                 [--format yaml|json] [--resolved] [--list-objects]

Options
-------

``--object``
  Show only this top-level key instead of the full config.

``--format`` *(yaml or json, default: yaml)*
  Output format. Use ``json`` for piping to ``jq`` or other tools.

``--resolved``
  Show the post-resolution config (objects instantiated, shown via ``repr``).

``--list-objects``
  List available top-level config keys.

Examples
--------

.. code-block:: bash

   # Pretty-print merged config
   sygaldry show -c base.yaml -c prod.yaml

   # Show a single object's config as JSON
   sygaldry show -c config.yaml --object db --format json

   # List available objects
   sygaldry show -c config.yaml --list-objects

validate
========

.. code-block:: text

   sygaldry validate -c CONFIG [--set K=V] [--use K=K]

Loads, merges, interpolates, and resolves the full config. Prints a success
message if valid, or an error with context if not. Useful for CI pipelines.

.. code-block:: bash

   sygaldry validate -c config.yaml

check
=====

.. code-block:: text

   sygaldry check -c CONFIG [--set K=V] [--use K=K]
                  [--type-checker ty|basedpyright|pyright|mypy] [-v]

Generates equivalent Python source from the loaded config and runs a static
type checker on it. This catches wrong argument names, wrong argument types,
and type mismatches in ``_ref`` wiring without instantiating any objects.

Options
-------

``--type-checker`` *(ty, basedpyright, pyright, or mypy)*
  Which type checker to use. When omitted the first available checker is
  selected, preferring ``ty`` then ``basedpyright`` then ``pyright`` then
  ``mypy``. See :doc:`type-checking` for details.

``-v`` / ``--verbose``
  Show full tracebacks on error.

How it works
------------

#. The config is loaded, merged, and interpolated as usual.
#. For each ``_type`` entry, the checker generates a Python constructor call
   with the same arguments that would be passed at runtime.
#. ``_ref`` entries become variable references so the type checker can verify
   that the referenced object is compatible with the target parameter.
#. The generated source is written to a temporary file and passed to the
   selected type checker.
#. Errors are mapped back to config paths and printed.

Examples
--------

.. code-block:: bash

   # Auto-detect the type checker
   sygaldry check -c config.yaml

   # Use a specific checker
   sygaldry check -c config.yaml --type-checker pyright

   # Multiple configs with overrides
   sygaldry check -c base.yaml -c prod.yaml --set db.host=prod-db

interactive
===========

.. code-block:: text

   sygaldry interactive -c CONFIG [--set K=V] [--use K=K] [-v]

Loads and merges the config, then drops into an interactive Python REPL with
the ``Artificery`` instance ready to use. This is useful for exploring a
config, inspecting resolved objects, or experimenting with the object graph.

Options
-------

``-v`` / ``--verbose``
  Show full tracebacks on error.

Available variables
-------------------

``artificery``
  The :class:`~sygaldry.Artificery` instance with config loaded and merged.

``Artificery``
  The :class:`~sygaldry.Artificery` class itself.

Examples
--------

.. code-block:: bash

   # Start a session with a single config
   sygaldry interactive -c config.yaml

   # Merge multiple configs and override a value
   sygaldry interactive -c base.yaml -c dev.yaml --set db.host=localhost

Inside the REPL:

.. code-block:: python

   >>> artificery.config                # view the interpolated config
   >>> artificery.resolve()             # resolve all objects
   >>> obj = artificery.resolve("db")   # resolve a single object

The ``_call`` key
=================

You can set default method and argument values in the config file itself using
the ``_call`` reserved key. This avoids having to pass ``--method`` and
arguments on every invocation.

.. code-block:: yaml

   pipeline:
     _type: "myapp.Pipeline"
     _call:
       method: "execute"
       args:
         - "daily"
     db: { _ref: "db" }

With this config:

.. code-block:: bash

   # Calls pipeline.execute("daily")
   sygaldry run -c config.yaml pipeline

   # Override method: calls pipeline.run("daily")
   sygaldry run -c config.yaml pipeline --method run

   # Override args: calls pipeline.execute(100, "weekly")
   sygaldry run -c config.yaml pipeline -- 100 weekly

CLI ``--method`` overrides ``_call.method``. Arguments after ``--`` override
``_call.args``.

Override and substitution order
===============================

The CLI processes config in this order:

#. **Load** each ``-c`` file (with ``_include`` expansion).
#. **Deep-merge** files left to right.
#. **Apply** ``--use`` substitutions (copies raw values within the config).
#. **Apply** ``--set`` overrides (explicit values win last).
#. **Interpolate** ``${...}`` placeholders.
#. **Extract** ``_call`` defaults for the target object.
#. **Resolve** component definitions into live objects.
#. **Call** the selected method with the final arguments.

Because ``--set`` and ``--use`` are applied before interpolation, any
``${...}`` references elsewhere in the config will pick up the overridden
values.
