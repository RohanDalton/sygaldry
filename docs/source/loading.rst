=======
Loading
=======

Includes
========

Use ``_include`` to merge additional config files. Includes load first, then
the current file overrides. The merge strategy is:

* dicts merge recursively
* lists/scalars replace

.. code-block:: yaml

   _include:
     - base.yaml
     - prod.yaml

Paths are resolved relative to the including file.

Interpolation
=============

Interpolation runs after includes and before resolution.

Resolution order
----------------

For each ``${key}`` placeholder, Sygaldry resolves the value using the
following priority:

#. **Config path** -- if ``key`` exists as a dotted path in the merged config,
   that value is used.
#. **Environment variable** -- if no config path matches, ``os.environ`` is
   checked.
#. **Default** -- if a default is provided via ``${key:-default}`` and neither
   config nor env matched, the default is used (and may itself contain
   nested placeholders).

If none of the above produce a value, an ``InterpolationError`` is raised.

Supported forms
---------------

* ``${config.path}`` -- value from merged config
* ``${ENV_VAR}`` -- environment variable (when not a config path)
* ``${key:-default}`` -- default when neither config nor env matches
* ``$${`` -- escape to a literal ``${``
* Nested placeholders are supported (e.g., ``${DB_HOST:-${db.host}}``)

Type coercion
-------------

If the entire string is replaced by a single placeholder, Sygaldry will try to
coerce the value to a scalar type (int, float, bool, or None).

Example
-------

.. code-block:: yaml

   db:
     host: "localhost"
     port: "${DB_PORT:-5432}"
   url: "postgres://${db.host}:${db.port}/app"
