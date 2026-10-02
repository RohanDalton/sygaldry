=======
Caching
=======

Each config node has its own identity for the lifetime of an ``Artificery``
instance. Repeated resolution and ``_ref`` aliases return that node's original
object. Two unnamed nodes with identical specs remain independent, including
mutable sources, cursors, and rate limiters.

Explicit sharing
================

Use ``_instance`` to share a component deliberately. Named entries are keyed
by ``(type_path, instance_tag)``. Reusing a tag with incompatible constructor
arguments, dependencies, or lifecycle settings raises ``ConfigConflictError``.
Constructor specs are compared before opening resources; concurrent requests
for the same named entry construct it once.

A supplied ``Instances`` cache owns named resources and their inline managed
dependencies. Its scope must surround every runtime using those resources:

.. code-block:: python

   from sygaldry import Artificery
   from sygaldry.cache import Instances

   async with Instances() as shared:
       async with Artificery("config.yaml", cache=shared) as first:
           source = await first.aresolve("source")
       # Named resources remain open after the first runtime closes.
       async with Artificery("config.yaml", cache=shared) as second:
           same_source = await second.aresolve("source")
           assert same_source is source
   # The shared cache closes named resources exactly once.

An unnamed resource belongs to its runtime. A named component must not borrow
a runtime-owned resource: give that dependency its own ``_instance``
tag, place it inline in the shared component, or explicitly use external
ownership. This prevents a cached component outliving its dependencies.
Shared managed resources use one event loop for construction, use, and cleanup.
Synchronous cache scopes keep that loop alive across their runtime scopes.

Without a supplied cache, ``Artificery`` creates and owns a private cache.
Closing the runtime closes both its unnamed resources and its private cache.
Requests through closed runtimes or caches raise ``LifecycleError``.

Transient resolution
====================

``transient=True`` isolates named entries from a supplied cache by using a
private cache. It preserves per-node identity and named sharing within that
runtime. It does not create a new object every time a reference is followed.
Use another ``Artificery`` instance when you need another independent graph.
