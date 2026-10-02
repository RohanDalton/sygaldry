__author__ = "Rohan B. Dalton"

import copy
import http.server
import threading
from functools import partial

import pytest
from click.testing import CliRunner


@pytest.fixture()
def served_config_directory(tmp_path):
    """Serve config fixtures over HTTP and close the server after each test."""
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture()
def lifecycle_events(mocker):
    """Keep fake resource events isolated between tests."""
    events = list()
    mocker.patch("tests.components.EVENTS", events)
    return events


@pytest.fixture()
def cli_runner():
    runner = CliRunner()
    return runner


_RESOURCE_CASES = {
    "sync_context": {"_type": "tests.components.SyncResource"},
    "async_context": {"_type": "tests.components.AsyncResource"},
    "async_factory": {"_type": "tests.components.create_resource"},
    "sync_close": {"_type": "tests.components.CloseResource"},
    "async_close": {"_type": "tests.components.AsyncCloseResource"},
}


@pytest.fixture(params=_RESOURCE_CASES)
def resource_spec(request):
    result = copy.deepcopy(_RESOURCE_CASES[request.param])
    return result


@pytest.fixture(params=[False, True])
def transient(request):
    result = request.param
    return result


_IDENTIFIER_CASES = {
    "account": {"value": "000123"},
    "cusip": {"value": "037833100"},
    "signed": {"value": "+000123"},
}


@pytest.fixture(params=_IDENTIFIER_CASES)
def identifier(request):
    result = copy.deepcopy(_IDENTIFIER_CASES[request.param])
    return result


_DISPLAY_CASES = {
    "yaml": ["show", "--raw"],
    "json": ["show", "--raw", "--format", "json"],
    "python": ["show"],
    "resolved": ["show", "--resolved"],
    "dry_run": ["run", "resource", "--dry-run"],
}


@pytest.fixture(params=_DISPLAY_CASES)
def display_arguments(request):
    result = copy.deepcopy(_DISPLAY_CASES[request.param])
    return result


@pytest.fixture(params=[False, True])
def dependent_first(request):
    result = request.param
    return result


if __name__ == "__main__":
    pass
