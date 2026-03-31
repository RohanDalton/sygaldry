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
* Extra kwargs are dropped with a warning (unless ``**kwargs`` is accepted).

References
==========

``_ref`` values can point to a top-level key or to an attribute on a resolved
object using dotted notation.

.. code-block:: yaml

   db:
     _type: "myapp.db.Database"
     host: "localhost"
     port: 5432

   pool_size:
     _ref: "db.pool.size"
