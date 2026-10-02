"""Observable fake components for identity and lifecycle regression tests."""

__author__ = "Rohan B. Dalton"

import asyncio

EVENTS = list()


class Plain:
    def __init__(self, name: str = "plain", rps: int = 5, table=None):
        EVENTS.append(("construct", name))
        self.name = name
        self.rps = rps
        self.table = table if table is not None else dict()


class SyncResource(Plain):
    def __enter__(self):
        EVENTS.append(("open", self.name))
        result = self
        return result

    def __exit__(self, exception_type, exception, traceback):
        EVENTS.append(("close", self.name))


class AsyncResource(Plain):
    async def __aenter__(self):
        await asyncio.sleep(0)
        self.loop = asyncio.get_running_loop()
        EVENTS.append(("open", self.name))
        result = self
        return result

    async def __aexit__(self, exception_type, exception, traceback):
        assert self.loop is asyncio.get_running_loop()
        EVENTS.append(("close", self.name))


class CloseResource(Plain):
    def close(self):
        EVENTS.append(("close", self.name))


class AsyncCloseResource(Plain):
    async def aclose(self):
        await asyncio.sleep(0)
        EVENTS.append(("close", self.name))


async def create_resource(name: str = "factory"):
    await asyncio.sleep(0)
    result = AsyncResource(name=name)
    return result


def fail():
    raise RuntimeError("construction failed")


class CallableResource(AsyncResource):
    async def __call__(self):
        EVENTS.append(("call", self.name))
        result = "complete"
        return result


class OpenResource(AsyncCloseResource):
    async def aopen(self):
        await asyncio.sleep(0)
        EVENTS.append(("open", self.name))


class FailingOpenResource(AsyncCloseResource):
    async def aopen(self):
        EVENTS.append(("open", self.name))
        raise RuntimeError("opening failed")


async def delayed_factory(name: str = "waiting"):
    EVENTS.append(("waiting", name))
    await asyncio.sleep(3600)
    result = Plain(name)
    return result


if __name__ == "__main__":
    pass
