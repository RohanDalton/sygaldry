__author__ = "Rohan B. Dalton"

import pytest

from sygaldry.cache import Instances
from sygaldry.errors import ConfigConflictError


def test_cache_reuses_instance_for_same_spec():
    """
    GIVEN: The same constructor spec used twice.
    WHEN:  Resolving via the cache.
    THEN:  The same instance is returned both times.
    """
    cache = Instances()
    created = list()

    def factory():
        obj = object()
        created.append(obj)
        return obj

    first = cache.get_or_create("demo.Type", None, (), {"a": 1}, factory)
    second = cache.get_or_create("demo.Type", None, (), {"a": 1}, factory)

    assert first is second
    assert created == [first]


def test_cache_conflict_for_same_key_with_different_spec():
    """
    GIVEN: A named instance already cached with one spec.
    WHEN:  Requesting the same instance tag with a different spec.
    THEN:  A ConfigConflictError is raised.
    """
    cache = Instances()

    def factory():
        return object()

    cache.get_or_create("demo.Type", "primary", (), {"a": 1}, factory)

    with pytest.raises(ConfigConflictError):
        cache.get_or_create("demo.Type", "primary", (), {"a": 2}, factory)


def test_cache_handles_none_return_value():
    """
    GIVEN: A factory that returns None.
    WHEN:  Caching the result and requesting it again.
    THEN:  None is cached and the factory is only called once.
    """
    cache = Instances()
    call_count = 0

    def factory():
        nonlocal call_count
        call_count += 1
        return None

    first = cache.get_or_create("demo.Type", "singleton", (), {}, factory)
    second = cache.get_or_create("demo.Type", "singleton", (), {}, factory)

    assert first is None
    assert second is None
    assert call_count == 1


def test_transient_bypasses_cache():
    """
    GIVEN: Transient mode enabled.
    WHEN:  Resolving the same spec multiple times.
    THEN:  A new instance is created each time.
    """
    cache = Instances()

    def factory():
        return object()

    first = cache.get_or_create("demo.Type", None, (), {"a": 1}, factory, transient=True)
    second = cache.get_or_create("demo.Type", None, (), {"a": 1}, factory, transient=True)
    third = cache.get_or_create("demo.Type", None, (), {"a": 1}, factory, transient=False)

    assert first is not second
    assert third is not first


if __name__ == "__main__":
    pass
