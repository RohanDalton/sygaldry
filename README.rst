========
Sygaldry
========

   *whereby an artificer uses runes and delicate metalwork to create items
   capable of amazing feats.*

Sygaldry is a Python library for building arbitrary object graphs from YAML or
TOML configuration files. It is designed for teams that run many similar
scheduled jobs and want to write reusable components, then compose them through
configuration rather than code.

Features
========

* **YAML and TOML** configuration with deep-merge includes.
* **Interpolation** -- ``${VAR}`` placeholders resolved from config paths,
  environment variables, or defaults.
* **Component instantiation** -- ``_type`` mappings construct classes,
  ``_func`` mappings import callables.
* **References** -- ``_ref`` wires components together by name or dotted
  attribute path.
* **Instance caching** -- identical specs share instances; named
  ``_instance`` tags give explicit control.
* **Safety** -- no ``eval``, no arbitrary code; imports are by dotted path
  only.

Installation
============

.. code-block:: bash

   pip install sygaldry

Quick start
===========

Define your components in a YAML file:

.. code-block:: yaml

   # config.yaml
   db:
     _type: "myapp.db.Database"
     host: "${DB_HOST:-localhost}"
     port: 5432

   service:
     _type: "myapp.services.UserService"
     db: { _ref: "db" }

Then load and resolve:

.. code-block:: python

   from sygaldry import load

   graph = load("config.yaml")
   service = graph["service"]   # a fully wired UserService instance

Or use the ``Artificery`` class for more control:

.. code-block:: python

   from sygaldry import Artificery

   factory = Artificery("config.yaml", transient=True)
   graph = factory.resolve()



License
=======

MIT
