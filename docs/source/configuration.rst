=============
Configuration
=============

Reserved keys
=============

``_type`` (str)
  Fully-qualified dotted path to a class to instantiate.

``_func`` (str)
  Fully-qualified dotted path to a callable. The callable is returned, not invoked.

``_args`` (list)
  Positional arguments for the constructor.

``_kwargs`` (dict)
  Extra keyword arguments for the constructor. Useful for passing arguments
  to functions that accept ``**kwargs``, especially when the key names
  conflict with reserved keys.

``_instance`` (str)
  Instance tag used to disambiguate cache entries. If omitted, caching
  is keyed by the constructor spec hash instead.

``_ref`` (str)
  Reference to a top-level entry (optionally with dotted attributes).

``_deep`` (bool)
  If ``false``, the resolver returns the dict as-is without recursion.
  The ``_deep`` key itself is stripped from the returned mapping.

``_include`` (list)
  Include other config files at load time. Included files are loaded
  and deep-merged before the current file's own keys.

``_entries`` (list)
  Use to define dict keys that are dynamically resolved.

``_call`` (dict)
  Default method and arguments for the CLI. Contains optional keys
  ``method`` (str) and ``args`` (list). See :doc:`cli`.

Rules
=====

* ``_type`` and ``_func`` are mutually exclusive.
* ``_ref`` must be the only key in its mapping.
* ``_func`` must be the only key in its mapping.
* ``_instance`` only applies to ``_type``.
* Non-reserved keys on a ``_type`` mapping are treated as kwargs.

YAML example
============

.. code-block:: yaml

   service:
     _type: "myapp.services.UserService"
     _args: ["primary"]
     db:
       _type: "myapp.db.Database"
       host: "localhost"
       port: 5432
     cache:
       _type: "myapp.cache.RedisCache"
       url: "redis://localhost:6379"

TOML example
============

.. code-block:: toml

   [service]
   _type = "myapp.services.UserService"
   _args = ["primary"]

   [service.db]
   _type = "myapp.db.Database"
   host = "localhost"
   port = 5432

   [service.cache]
   _type = "myapp.cache.RedisCache"
   url = "redis://localhost:6379"

References
==========

.. code-block:: yaml

   database:
     _type: "myapp.db.Database"
     host: "localhost"

   user_service:
     _type: "myapp.services.UserService"
     db: { _ref: "database" }

Dotted refs access attributes on the referenced object:

.. code-block:: yaml

   pool_size:
     _ref: "database.connection_pool.size"

Entries for non-string keys
===========================

If a dict key needs to be resolved (including references), use ``_entries``:

.. code-block:: yaml

   map:
     _entries:
       - _key: { _ref: "some.key" }
         _value: 123

Extra keyword arguments
=======================

Use ``_kwargs`` to pass a mapping of keyword arguments to constructors that
accept ``**kwargs``:

.. code-block:: yaml

   handler:
     _type: "myapp.handlers.FlexibleHandler"
     name: "main"
     _kwargs:
       color: "red"
       size: 42

This is equivalent to calling
``FlexibleHandler(name="main", color="red", size=42)``.

``_kwargs`` entries are merged with any non-reserved keys on the same mapping.
This is useful when a keyword argument name would collide with a reserved key
like ``_type`` or ``_ref``.

Dotted key overrides
====================

Top-level keys containing dots are expanded into nested dicts before merging.
This provides a compact way to override deeply nested values, especially
in combination with ``_include``:

.. code-block:: yaml

   # sftp.yaml
   ftp_client:
     host: null
     port: 22
     password: "correct-horse-battery-staple"
     timeout: 3600

.. code-block:: yaml

   # vendor.yaml
   _include:
     - sftp.yaml

   ftp_client.host: "foo.com"
   ftp_client.timeout: 100

After loading ``vendor.yaml``, ``ftp_client.host`` is ``"foo.com"``,
``ftp_client.timeout`` is ``100``, and the remaining keys (``port``,
``password``) are inherited from ``sftp.yaml``.
