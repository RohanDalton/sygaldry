=======
Caching
=======

Sygaldry caches constructed instances per factory instance. The cache key is:

* ``(type_path, instance_tag)`` when ``_instance`` is provided.
* ``(type_path, spec_hash)`` when ``_instance`` is omitted.

The cache hash is computed from resolved args and kwargs using a canonical
normalization (including object identity markers for non-JSON values) and
SHA-256. If a key with an explicit ``_instance`` is reused with a different
hash, a ``ConfigConflictError`` is raised.

Transient resolution
====================

Set ``transient=True`` to bypass caching and always construct new instances.

Example
=======

.. code-block:: python

   from sygaldry import Artificery

   factory = Artificery("config.yaml", transient=True)
   graph = factory.resolve()
