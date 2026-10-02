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
* **Explicit sharing** -- nodes are independent by default; named
  ``_instance`` tags share resources within a cache lifetime.
* **Managed lifetimes** -- sync and async runtime scopes await factories and
  close resources in dependency order.
* **Strict validation** -- check signatures without constructing objects;
  diagnose unknown arguments and protect secret values in displays.
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
