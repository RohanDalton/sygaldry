from sygaldry.environment import Environment

__author__ = "Rohan"


def test_single_env():
    first = Environment()
    second = Environment()
    assert first is second


if __name__ == "__main__":
    pass
