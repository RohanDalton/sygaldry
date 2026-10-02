================
Resolution rules
================

Resolution walks the config tree depth-first and constructs child components
before their parents. Each value is resolved using the following order:

#. Mapping with ``_ref``: resolve reference target.
#. Mapping with ``_type``: resolve children, then instantiate.
#. Mapping with ``_func``: import callable and return it (do not call).
   Extra keys alongside ``_func`` raise a ``ValidationError``.
#. Mapping with ``_deep: false``: return dict as-is (``_deep`` key stripped).
#. Mapping with ``_entries``: resolve key/value entries.
#. Plain mapping: resolve values.
#. List/tuple: resolve each element.
#. Scalar: pass through.

Signature validation
====================

Sygaldry validates constructor signatures:

* Missing required parameters raise a ``ConstructorError``.
* Unknown kwargs raise a ``ConstructorError`` by default. Callables accepting
  ``**kwargs`` keep those arguments. Set ``strict=False`` or pass ``--no-strict``
  for compatibility mode, which warns and drops unknown arguments.

References
==========

``_ref`` values traverse nested mapping keys, list or tuple indexes, and
attributes on constructed objects using dotted notation. References preserve
the target node identity in every cache mode.

.. code-block:: yaml

   db:
     _type: "myapp.db.Database"
     host: "localhost"
     port: 5432

   pool_size:
     _ref: "db.pool.size"

Runtime scopes and async factories
==================================

Managed resources require a ``with`` or ``async with`` scope. Each runtime
owns an ``AsyncExitStack`` and closes its resources in reverse dependency
order on normal exit, exceptions, and cancellation. Named resources follow
the cache lifetime described in :doc:`caching`.

.. code-block:: python

   from sygaldry import Artificery

   async with Artificery("config.yaml") as runtime:
       writer = await runtime.aresolve("writers.vendor_a")
       await writer.run()

``_type`` may refer to a synchronous callable or an async factory. Awaitable
construction results are awaited on the runtime's event loop. ``_func``
continues to return the callable itself. The synchronous API also supports
async factories and cleanup:

.. code-block:: python

   with Artificery("config.yaml") as runtime:
       writer = runtime.resolve("writers.vendor_a")
       writer.run()

Inside an existing event loop, use ``aresolve`` and ``async with``. The runtime
also exposes ``close`` and ``aclose``; explicit scopes ensure cleanup on failure.
The convenience ``load`` and ``resolve_config`` functions support unscoped
components. Use ``Artificery`` scopes for managed resources.

Lifecycle policy
----------------

``_lifecycle`` accepts these policies:

* ``auto`` (default): prefer the async context protocol, then the synchronous
  context protocol. Otherwise register ``aclose`` or ``close`` and invoke
  ``aopen`` or ``open`` if provided.
* ``context``: require a context manager and use its entered value.
* ``close``: register ``aclose`` or ``close`` without opening the component.
* ``external``: leave opening and cleanup to the caller.

Selective resolution and validation
===================================

``resolve("group.source")`` and ``await aresolve("group.source")`` resolve
only that node and its dependencies. Unrelated components are not imported or
constructed. A later full resolution reuses the same node objects.

``validate()`` checks schemas, imports, references, cycles, and constructor
signatures without invoking constructors or lifecycle hooks. Pass a dotted
key to validate only its dependency graph. Imports can execute module-level
Python code, so validation is construction-free rather than a sandbox.
