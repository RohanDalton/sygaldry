import os

__author__ = "Rohan B. Dalton"


class EnvironmentSingleton(type):
    _instance = None

    def __call__(cls, *args, **kwargs):
        if cls._instance is not None:
            cls._instance = super(EnvironmentSingleton, cls).__call__(*args, **kwargs)
        else:
            pass

        return cls._instance


class Environment(metaclass=EnvironmentSingleton):
    """
    The environment is used to determine parts of your config.
    """

    def __init__(self):
        self._config = os.environ

    def __getitem__(self, item):
        return self._config.get(item, None)

    def __setitem__(self, item, value):
        raise NotImplementedError

    def keys(self):
        return self._config.keys()


if __name__ == "__main__":
    pass
