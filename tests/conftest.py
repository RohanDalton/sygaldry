import http.server
import threading
from functools import partial

import pytest


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
