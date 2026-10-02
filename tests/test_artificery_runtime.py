__author__ = "Rohan B. Dalton"

import asyncio

import pytest

from sygaldry import Artificery
from sygaldry.cache import Instances
from sygaldry.errors import (
    CircularReferenceError,
    ConfigConflictError,
    ConstructorError,
    InterpolationError,
    LifecycleError,
    ValidationError,
)


def test_equal_unnamed_nodes_are_independent(lifecycle_events, transient):
    """
    Given: Two structurally identical unnamed rate limiters.
    When:  Resolving their graph in either cache mode.
    Then:  Each node owns a distinct object and budget.
    """
    config = {
        "vendor_a": {"_type": "tests.components.Plain"},
        "vendor_b": {"_type": "tests.components.Plain"},
    }
    actual = Artificery(config=config, transient=transient).resolve()
    assert actual["vendor_a"] is not actual["vendor_b"]
    assert len(lifecycle_events) == 2


def test_refs_preserve_nested_node_identity(lifecycle_events, transient):
    """
    Given: A source in a nested mapping and multiple references to its table.
    When:  Resolving the graph in either cache mode.
    Then:  The source is constructed once and writers share the same table.
    """
    config = {
        "group": {"source": {"_type": "tests.components.Plain"}},
        "alias": {"_ref": "group.source"},
        "writer": {"_type": "tests.components.Plain", "table": {"_ref": "group.source.table"}},
    }
    actual = Artificery(config=config, transient=transient).resolve()
    assert actual["alias"] is actual["group"]["source"]
    assert actual["writer"].table is actual["group"]["source"].table
    assert len(lifecycle_events) == 2


def test_transient_sharing_is_local_to_runtime(lifecycle_events):
    """
    Given: Two named specs and a cache passed to two transient runtimes.
    When:  Resolving both graphs.
    Then:  Named identity is preserved within each graph and isolated between graphs.
    """
    cache = Instances()
    config = {
        "first": {"_type": "tests.components.Plain", "_instance": "shared"},
        "second": {"_type": "tests.components.Plain", "_instance": "shared"},
    }
    first = Artificery(config=config, cache=cache, transient=True).resolve()
    second = Artificery(config=config, cache=cache, transient=True).resolve()
    assert first["first"] is first["second"]
    assert second["first"] is second["second"]
    assert first["first"] is not second["first"]


def test_selected_resolution_skips_unrelated_nodes(lifecycle_events):
    """
    Given: One valid nested node and an unrelated invalid import.
    When:  Resolving just the selected dotted key.
    Then:  Only the selected node and its dependencies are validated and constructed.
    """
    config = {
        "group": {
            "selected": {"_type": "tests.components.Plain"},
            "unrelated": {"_type": "no_such_module.Client"},
        }
    }
    runtime = Artificery(config=config)
    actual = runtime.resolve("group.selected")
    assert actual is runtime.resolve("group.selected")
    assert len(lifecycle_events) == 1


def test_refs_traverse_plain_lists_and_dicts():
    """
    Given: References into a list nested inside a plain mapping.
    When:  Resolving the graph.
    Then:  Mapping keys and sequence indexes resolve consistently.
    """
    expected = {"group": {"values": ["first", "second"]}, "alias": "second"}
    actual = Artificery(
        config={"group": {"values": ["first", "second"]}, "alias": {"_ref": "group.values.1"}}
    ).resolve()
    assert actual == expected


def test_nested_refs_detect_cycles():
    """
    Given: Two nested nodes referencing one another.
    When:  Validating their graph.
    Then:  A circular reference is reported before construction.
    """
    runtime = Artificery(
        config={"group": {"a": {"_ref": "group.b"}, "b": {"_ref": "group.a"}}}
    )
    with pytest.raises(CircularReferenceError):
        runtime.validate()


def test_validate_never_constructs(lifecycle_events, resource_spec):
    """
    Given: A valid resource constructor or async factory.
    When:  Validating its configuration.
    Then:  No constructor, open, or close hook runs.
    """
    runtime = Artificery(config={"resource": resource_spec})
    runtime.validate()
    assert lifecycle_events == list()


def test_strict_validation_rejects_typo_before_construction(lifecycle_events):
    """
    Given: A misspelled constructor keyword.
    When:  Resolving in default strict mode.
    Then:  Validation fails before constructing any object.
    """
    runtime = Artificery(config={"resource": {"_type": "tests.components.Plain", "rpps": 5}})
    with pytest.raises(ConstructorError, match="rpps"):
        runtime.resolve()
    assert lifecycle_events == list()


def test_nonstrict_mode_warns_and_filters_unknown_kwargs(lifecycle_events):
    """
    Given: A misspelled keyword and explicit compatibility mode.
    When:  Resolving the selected node.
    Then:  A warning explains that the unknown argument is ignored.
    """
    runtime = Artificery(
        config={"resource": {"_type": "tests.components.Plain", "rpps": 5}}, strict=False
    )
    with pytest.warns(RuntimeWarning, match="rpps"):
        actual = runtime.resolve("resource")
    assert actual.rps == 5
    assert len(lifecycle_events) == 1


def test_sync_scope_closes_owned_resources(lifecycle_events, resource_spec):
    """
    Given: A resource spec in a synchronous runtime scope.
    When:  Resolving it and then leaving the scope.
    Then:  Its context or close hook runs exactly once.
    """
    with Artificery(config={"resource": {**resource_spec, "name": "selected"}}) as runtime:
        actual = runtime.resolve("resource")
        assert actual is runtime.resolve("resource")
        assert ("close", "selected") not in lifecycle_events
    assert lifecycle_events.count(("close", "selected")) == 1
    with pytest.raises(LifecycleError):
        runtime.resolve()


def test_async_scope_closes_resources_in_reverse_dependency_order(lifecycle_events):
    """
    Given: An async source and a dependent async writer sharing its table.
    When:  Resolving and leaving an asynchronous runtime scope.
    Then:  The writer closes before the source on the same event loop.
    """
    config = {
        "source": {"_type": "tests.components.AsyncResource", "name": "source"},
        "writer": {
            "_type": "tests.components.AsyncResource",
            "name": "writer",
            "table": {"_ref": "source.table"},
        },
    }

    async def scenario():
        async with Artificery(config=config) as runtime:
            graph = await runtime.aresolve()
            assert graph["source"].table is graph["writer"].table

    asyncio.run(scenario())
    assert lifecycle_events[-2:] == [("close", "writer"), ("close", "source")]


def test_scope_cleans_up_after_failed_construction(lifecycle_events):
    """
    Given: A resource followed by a constructor that fails.
    When:  Resolving the graph inside a runtime scope.
    Then:  Already opened resources close as the scope unwinds.
    """
    config = {
        "first": {"_type": "tests.components.AsyncResource", "name": "first"},
        "second": {"_type": "tests.components.fail"},
    }
    with pytest.raises(ConstructorError), Artificery(config=config) as runtime:
        runtime.resolve()
    assert lifecycle_events[-1] == ("close", "first")


def test_cache_owns_shared_cleanup(lifecycle_events):
    """
    Given: Two scoped runtimes borrowing one named resource from a shared cache.
    When:  Both runtimes close before the cache.
    Then:  Only closing the cache closes the resource, exactly once.
    """
    config = {
        "resource": {
            "_type": "tests.components.SyncResource",
            "name": "shared",
            "_instance": "shared",
        }
    }
    with Instances() as cache:
        with Artificery(config=config, cache=cache) as first_runtime:
            first = first_runtime.resolve("resource")
        with Artificery(config=config, cache=cache) as second_runtime:
            second = second_runtime.resolve("resource")
            assert first is second
        assert ("close", "shared") not in lifecycle_events
    assert lifecycle_events.count(("close", "shared")) == 1


def test_closed_shared_cache_is_rejected(lifecycle_events):
    """
    Given: A named resource whose cache scope has closed.
    When:  Another runtime requests the cached resource.
    Then:  A lifecycle error prevents returning a closed object.
    """
    config = {"resource": {"_type": "tests.components.SyncResource", "_instance": "shared"}}
    with Instances() as cache, Artificery(config=config, cache=cache) as creator:
        creator.resolve()
    with pytest.raises(LifecycleError), Artificery(config=config, cache=cache) as borrower:
        borrower.resolve()


def test_external_lifecycle_borrows_without_cleanup(lifecycle_events):
    """
    Given: A resource explicitly marked external.
    When:  Resolving it without a runtime scope.
    Then:  The caller owns opening and closing the resource.
    """
    actual = Artificery(
        config={
            "resource": {"_type": "tests.components.SyncResource", "_lifecycle": "external"}
        }
    ).resolve("resource")
    assert actual.name == "plain"
    assert lifecycle_events == [("construct", "plain")]


def test_unscoped_managed_class_fails_before_construction(lifecycle_events):
    """
    Given: A managed class requested without a runtime scope.
    When:  Resolving that resource.
    Then:  No constructor or lifecycle hook runs.
    """
    with pytest.raises(LifecycleError, match="require"):
        Artificery(config={"resource": {"_type": "tests.components.SyncResource"}}).resolve()
    assert lifecycle_events == list()


def test_async_named_creation_is_serialized(lifecycle_events):
    """
    Given: Two simultaneous requests for one named async factory.
    When:  Resolving from separate runtimes sharing a cache on one loop.
    Then:  The factory runs once and the cache owns cleanup.
    """
    cache = Instances()
    config = {"resource": {"_type": "tests.components.create_resource", "_instance": "shared"}}

    async def scenario():
        async with (
            cache,
            Artificery(config=config, cache=cache) as first,
            Artificery(config=config, cache=cache) as second,
        ):
            values = await asyncio.gather(
                first.aresolve("resource"), second.aresolve("resource")
            )
            assert values[0] is values[1]

    asyncio.run(scenario())
    assert lifecycle_events.count(("construct", "factory")) == 1
    assert lifecycle_events.count(("close", "factory")) == 1


def test_dict_config_applies_overrides_uses_and_interpolation():
    """
    Given: An in-memory config with placeholders, uses, and overrides.
    When:  Preparing it.
    Then:  It follows the file pipeline without modifying the caller's input.
    """
    original = {"host": "original", "endpoint": "${host}", "copy": "${selected}"}
    expected = {
        "host": "updated",
        "endpoint": "updated",
        "copy": "original",
        "selected": "original",
    }
    actual = Artificery(
        config=original, uses={"selected": "host"}, overrides={"host": "updated"}
    ).config
    assert actual == expected
    assert original["host"] == "original"


def test_layered_constructor_error_names_defining_file(tmp_path):
    """
    Given: A base file with a bad keyword and a later file changing another key.
    When:  Validating the layered config.
    Then:  The diagnostic identifies the file defining the bad keyword.
    """
    base_path = tmp_path / "base.yaml"
    overlay_path = tmp_path / "overlay.yaml"
    base_path.write_text(
        "resource:\n  _type: tests.components.Plain\n  rpps: 5\n", encoding="utf-8"
    )
    overlay_path.write_text("resource:\n  name: overlay\n", encoding="utf-8")
    with pytest.raises(ConstructorError) as error:
        Artificery(base_path, overlay_path).validate()
    assert error.value._file_path == str(base_path)
    assert error.value._config_path == "resource.rpps"


def test_included_interpolation_error_names_original_file(tmp_path):
    """
    Given: A bad placeholder in an included file and an unrelated overlay.
    When:  Preparing the config.
    Then:  The error identifies the included file rather than the overlay.
    """
    included_path = tmp_path / "included.yaml"
    root_path = tmp_path / "root.yaml"
    included_path.write_text("bad: '${NO_SUCH_VALUE}'\n", encoding="utf-8")
    root_path.write_text("_include:\n  - included.yaml\nother: ok\n", encoding="utf-8")
    with pytest.raises(InterpolationError) as error:
        _ = Artificery(root_path).config
    assert error.value._file_path == str(included_path)


def test_inline_shared_dependencies_belong_to_cache(lifecycle_events):
    """
    Given: A named component with an inline unnamed resource dependency.
    When:  Two runtimes borrow it and then close before the cache.
    Then:  The dependency is created once and remains open until cache shutdown.
    """
    config = {
        "parent": {
            "_type": "tests.components.Plain",
            "_instance": "parent",
            "table": {"_type": "tests.components.SyncResource", "name": "child"},
        }
    }
    with Instances() as cache:
        with Artificery(config=config, cache=cache) as first:
            expected = first.resolve("parent")
        with Artificery(config=config, cache=cache) as second:
            actual = second.resolve("parent")
        assert actual is expected
        assert ("close", "child") not in lifecycle_events
    assert lifecycle_events.count(("construct", "child")) == 1
    assert lifecycle_events.count(("close", "child")) == 1


def test_shared_resource_cannot_borrow_runtime_owned_dependency(
    lifecycle_events, dependent_first
):
    """
    Given: A named component referencing an unnamed source in either config order.
    When:  Resolving the graph with a shared cache.
    Then:  The runtime rejects the shorter dependency lifetime explicitly.
    """
    config = {
        "source": {"_type": "tests.components.SyncResource"},
        "writer": {
            "_type": "tests.components.Plain",
            "_instance": "writer",
            "table": {"_ref": "source.table"},
        },
    }
    if dependent_first:
        config = dict(reversed(tuple(config.items())))
    else:
        pass
    with (
        Instances() as cache,
        Artificery(config=config, cache=cache) as runtime,
        pytest.raises(LifecycleError, match="runtime-owned"),
    ):
        runtime.resolve()


def test_conflicting_recursive_instance_tag_does_not_deadlock():
    """
    Given: A named node depending on another spec with the same instance tag.
    When:  Resolving the node.
    Then:  A conflict is reported instead of waiting on its own cache claim.
    """
    config = {
        "parent": {
            "_type": "tests.components.Plain",
            "_instance": "recursive",
            "table": {"_type": "tests.components.Plain", "_instance": "recursive"},
        }
    }
    with pytest.raises(ConfigConflictError):
        Artificery(config=config).resolve()


def test_auto_lifecycle_opens_and_closes_hooks(lifecycle_events):
    """
    Given: A component exposing aopen and aclose rather than a context manager.
    When:  Resolving it in a managed scope.
    Then:  Opening occurs before use and closing occurs when the scope exits.
    """
    with Artificery(
        config={"resource": {"_type": "tests.components.OpenResource"}}
    ) as runtime:
        runtime.resolve()
        assert lifecycle_events[-1] == ("open", "plain")
    assert lifecycle_events[-1] == ("close", "plain")


def test_failed_open_hook_is_cleaned_up(lifecycle_events):
    """
    Given: A resource whose opening hook partially opens and then fails.
    When:  Resolving it in a managed scope.
    Then:  Its registered close hook still runs during unwinding.
    """
    with (
        pytest.raises(RuntimeError, match="opening failed"),
        Artificery(
            config={"resource": {"_type": "tests.components.FailingOpenResource"}}
        ) as runtime,
    ):
        runtime.resolve()
    assert lifecycle_events[-1] == ("close", "plain")


def test_cancellation_closes_already_open_resources(lifecycle_events):
    """
    Given: An opened resource followed by a factory that suspends indefinitely.
    When:  Construction is cancelled inside a managed scope.
    Then:  Open resources close and cancellation propagates.
    """
    config = {
        "source": {"_type": "tests.components.AsyncResource"},
        "delayed": {"_type": "tests.components.delayed_factory"},
    }

    async def scenario():
        async with Artificery(config=config) as runtime:
            task = asyncio.create_task(runtime.aresolve())
            while ("waiting", "waiting") not in lifecycle_events:
                await asyncio.sleep(0)
            task.cancel()
            await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scenario())
    assert lifecycle_events[-1] == ("close", "plain")


def test_layered_explicit_kwargs_error_names_defining_file(tmp_path):
    """
    Given: A typo under _kwargs in a base file and a later unrelated overlay.
    When:  Validating the layered config.
    Then:  The diagnostic names the base file and precise keyword path.
    """
    base = tmp_path / "base.yaml"
    overlay = tmp_path / "overlay.yaml"
    base.write_text(
        "resource:\n  _type: tests.components.Plain\n  _kwargs:\n    rpps: 5\n",
        encoding="utf-8",
    )
    overlay.write_text("resource:\n  name: overlay\n", encoding="utf-8")
    with pytest.raises(ConstructorError) as error:
        Artificery(base, overlay).validate()
    assert error.value._file_path == str(base)
    assert error.value._config_path == "resource._kwargs.rpps"


def test_provided_object_identity_is_preserved():
    """
    Given: An existing object in an in-memory config.
    When:  Preparing and resolving the config.
    Then:  The object is borrowed without being deep-copied.
    """
    expected = object()
    actual = Artificery(config={"provided": expected}).resolve("provided")
    assert actual is expected


def test_validation_and_resolution_agree_with_deep_false_on_constructor(lifecycle_events):
    """
    Given: A component with _deep false and a plain literal mapping beneath it.
    When:  Validating and resolving the selected component.
    Then:  Constructor validation still runs and literal nested data stays untouched.
    """
    config = {
        "resource": {
            "_type": "tests.components.Plain",
            "_deep": False,
            "table": {"_deep": False, "_type_literal": "not.a.constructor"},
        }
    }
    runtime = Artificery(config=config)
    runtime.validate()
    assert lifecycle_events == list()
    actual = runtime.resolve("resource")
    assert actual.table == {"_type_literal": "not.a.constructor"}


def test_invalid_secret_marker_is_rejected():
    """
    Given: A secret marker mixed with another key.
    When:  Validating the config.
    Then:  The ambiguous marker is rejected explicitly.
    """
    with pytest.raises(ValidationError, match="_secret must be the only key"):
        Artificery(config={"value": {"_secret": "private", "extra": "value"}}).validate()


def test_private_named_and_unnamed_resources_close_in_dependency_order(lifecycle_events):
    """
    Given: An unnamed source and a named writer in one private runtime.
    When:  The writer borrows the source and the runtime exits.
    Then:  Equal lifetimes allow the dependency and close the writer first.
    """
    config = {
        "source": {"_type": "tests.components.SyncResource", "name": "source"},
        "writer": {
            "_type": "tests.components.SyncResource",
            "name": "writer",
            "_instance": "writer",
            "table": {"_ref": "source.table"},
        },
    }
    with Artificery(config=config) as runtime:
        actual = runtime.resolve()
        assert actual["writer"].table is actual["source"].table
    assert lifecycle_events[-2:] == [("close", "writer"), ("close", "source")]


def test_non_strict_drops_unknown_values_without_resolving_them(lifecycle_events):
    """
    Given: A legacy unknown keyword containing an invalid component spec.
    When:  Resolving in compatibility mode.
    Then:  The ignored keyword warns without importing or constructing its value.
    """
    config = {
        "resource": {
            "_type": "tests.components.Plain",
            "obsolete": {"_type": "not_a_real_module.Resource"},
        }
    }
    with pytest.warns(RuntimeWarning, match="obsolete"):
        actual = Artificery(config=config, strict=False).resolve("resource")
    assert actual.name == "plain"
    assert lifecycle_events == [("construct", "plain")]


if __name__ == "__main__":
    pass
