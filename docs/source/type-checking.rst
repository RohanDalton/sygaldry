============
Type Checking
============

Sygaldry can statically type check your configuration *before* any objects are
instantiated. It generates equivalent Python source from the loaded config and
runs a type checker on it, catching wrong argument names, wrong argument types,
and ``_ref`` type mismatches early.

Supported Type Checkers
=======================

The following type checkers are supported, listed in auto-detection order:

#. `ty <https://github.com/astral-sh/ty>`_
#. `basedpyright <https://github.com/DetachHead/basedpyright>`_
#. `pyright <https://github.com/microsoft/pyright>`_
#. `mypy <https://github.com/python/mypy>`_

When no ``--type-checker`` is specified, sygaldry picks the first one it finds
on your ``PATH``.

Quick Start
===========

.. code-block:: bash

   # Auto-detect the type checker
   sygaldry check -c config.yaml

   # Use a specific checker
   sygaldry check -c config.yaml --type-checker basedpyright

How It Works
============

#. The config is loaded, merged, and interpolated as usual.
#. For each ``_type`` entry, sygaldry generates a Python constructor call with
   the same arguments that would be passed at runtime.
#. ``_ref`` entries become variable references so the type checker can verify
   that the referenced object is compatible with the target parameter.
#. The generated source is written to a temporary file and passed to the
   selected type checker.
#. Errors are mapped back to config paths and printed.

Example
=======

Given a config that wires up a database and a service:

.. code-block:: yaml

   db:
     _type: myapp.db.PostgresDB
     host: localhost
     port: 5432

   service:
     _type: myapp.svc.UserService
     database: {_ref: db}

Running the checker:

.. code-block:: bash

   sygaldry check -c config.yaml

If ``UserService.__init__`` expects a ``Database`` but ``db`` resolves to
something incompatible, the type checker will report the mismatch against the
``service`` config path.

Using with Overrides
====================

You can combine type checking with config overrides to validate specific
deployment configurations:

.. code-block:: bash

   # Check a production configuration
   sygaldry check -c base.yaml -c prod.yaml --set db.host=prod-db

   # Verbose output for debugging
   sygaldry check -c config.yaml -v

Programmatic Usage
==================

You can also run the checker from Python:

.. code-block:: python

   from sygaldry.checker import check

   errors = check("config.yaml")
   for err in errors:
       print(f"{err.severity}: {err.config_path}: {err.message}")

Pass a ``type_checker`` argument to force a specific checker:

.. code-block:: python

   errors = check("config.yaml", type_checker="basedpyright")
