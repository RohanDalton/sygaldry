=======
Loading
=======

Loading without instantiating components
========================================

Access ``Artificery.config`` to obtain the loaded, merged, and interpolated
mapping. Component definitions remain dictionaries until you call
``Artificery.resolve()``.

.. code-block:: python

   from sygaldry import Artificery

   artificery = Artificery(
       "base.yaml",
       "prod.yaml",
       overrides={"service.port": 8080},
   )
   config = artificery.config
   graph = artificery.resolve()

Config sources may be local YAML or TOML files or HTTP(S) URLs. Multiple
sources merge in order, followed by ``uses`` mappings, ``overrides``, and
interpolation. The prepared mapping is cached on the ``Artificery`` instance.

Migrating from the previous loading API
---------------------------------------

``sygaldry.loader`` and the ``load_config_file`` and ``ArtificeryLoader``
wrappers have been removed. Replace ``load_config(path)``,
``load_config_file(path)``, or ``ArtificeryLoader(path).load()`` with
``Artificery(path).config``. The implementation helpers in
``sygaldry.configuration`` are internal; use ``Artificery`` for loading.

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

Whole-value config references preserve the referenced value's existing type,
including quoted numeric strings. Environment values and literal defaults
coerce canonical numbers, booleans, and null values. Zero-prefixed identifiers
such as ``000123`` and ``037833100`` remain strings in YAML, interpolation,
and CLI overrides. Quote numeric strings in TOML, whose parser rejects
unquoted numbers with leading zeros.

Example
-------

.. code-block:: yaml

   db:
     host: "localhost"
     port: "${DB_PORT:-5432}"
   url: "postgres://${db.host}:${db.port}/app"

In-memory configs and source locations
======================================

``Artificery(config=...)`` follows the same uses, overrides, and interpolation
pipeline as file inputs. Preparing a config copies its containers without
mutating the supplied mapping or copying supplied application objects.

Diagnostics track the file defining each value through includes and layered
merges. An overlay changing another field does not relabel an earlier field's
error. Programmatic input uses ``source`` or ``<config>``; explicit overrides
use ``<override>``.

Secret values
=============

Common credential field names are protected automatically. Mark confidential
values under other names explicitly, including values passed in memory:

.. code-block:: yaml

   service:
     _type: myapp.Service
     password: confidential
     identifier:
       _secret: confidential-value

.. code-block:: python

   from sygaldry import Artificery, Secret

   runtime = Artificery(config={"private_value": Secret("confidential")})

All environment-derived values are protected, and their protection propagates
through config references and composed strings. Protected values remain
``Secret`` markers in ``config`` and are unwrapped when delivered to
constructors or resolved values. Their displayed representation is
``<redacted>``. Secret values cannot be mapping keys because paths and key
names appear in diagnostics.

``show``, ``show --raw``, ``show --resolved``, and ``run --dry-run`` mask
protected values. Generated type-checking source substitutes harmless values
of matching primitive types. Secrets therefore never enter the checker's
source file. Literal-dependent overload checks may differ when a placeholder
is substituted. Checker files are private and removed even if the checker
fails or times out. Application code still receives real secret values and
is responsible for its own logging.
