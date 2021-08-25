import pytest

from sygaldry import Artificery

__author__ = "Rohan"


def test_something(tmp_path):
    content = ""

    file_path = tmp_path.joinpath("test.yml")
    file_path.write_text(content)

    factory = Artificery(file_path=file_path)
    assert True


if __name__ == "__main__":
    pass
