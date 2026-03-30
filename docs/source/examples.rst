========
Examples
========

Simple service graph
====================

.. code-block:: yaml

   db:
     _type: "myapp.db.Database"
     host: "localhost"
     port: 5432

   cache:
     _type: "myapp.cache.RedisCache"
     url: "redis://localhost:6379"

   service:
     _type: "myapp.services.UserService"
     db: { _ref: "db" }
     cache: { _ref: "cache" }

.. code-block:: python

   from sygaldry import Artificery

   graph = Artificery("config.yaml").resolve()
   service = graph["service"]

Includes with overrides
=======================

.. code-block:: yaml

   # base.yaml
   service:
     host: "localhost"
     port: 9000

.. code-block:: yaml

   # prod.yaml
   _include:
     - base.yaml
   service:
     port: 9001

Interpolation and refs
======================

.. code-block:: yaml

   db:
     _type: "myapp.db.Database"
     host: "${DB_HOST:-localhost}"
     port: 5432

   url: "postgres://${db.host}:${db.port}/app"

Dict keys via _entries
======================

.. code-block:: yaml

   key:
     _type: "myapp.models.Key"
     name: "primary"

   map:
     _entries:
       - _key: { _ref: "key" }
         _value: 123

Static type checking
====================

Given the service graph above, run a type checker to catch wiring errors
before any objects are instantiated:

.. code-block:: bash

   sygaldry check -c config.yaml

The checker generates equivalent Python constructor calls and passes them to
``ty``, ``basedpyright``, ``pyright``, or ``mypy``. If ``UserService.__init__`` expects a
``PostgresDB`` but ``db`` resolves to a ``Database``, the type checker will
report the mismatch against the ``service`` config path.
