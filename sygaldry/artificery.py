import builtins
import importlib
import io
from pathlib import Path
from typing import Any, List, Optional, Union

import yaml
from jinja2 import Template

from sygaldry.environment import Environment

__author__ = "Rohan B. Dalton"

File = Union[str, Path]
Files = Union[File, List[File]]

# TODO: Jinja Templating
# TODO: Environment variables
# TODO: Support .ini and .yaml
# TODO: Return an object from a YAML file.
# TODO: Return a function from a YAML file.git 
# TODO: Return a variable from a YAML file? Also, what is an enum?
# TODO: Be able to return an instance of a type.
# TODO: Be able to pass multiple files into constructor
# TODO: Be able to pass overrides into constructor
# TODO: Be able to call objects from the command line?
# TODO: Have files be able to include another file.
# TODO: Need to be able to handle includes in a recursive and unique fashion. Order?
# TODO: Write custom YAML parser, or extension. Allow default module.
# TODO: Support arg only arguments

_module_ = "::module"
_type_ = "::type"
_value_ = "::value"


def _list_of_files(file_or_files) -> List[File]:
    if isinstance(file_or_files, (str, Path)):
        return [file_or_files]
    elif file_or_files is None:
        return list()
    else:
        return list(reversed(file_or_files))


class Artificery(object):
    """
    An :py:class:`~sygaldry.artificery.Artificery` is an an object factory.

    """

    def __init__(self, file_path: File, *, additional_files: Optional[Files] = None, env: Union[bool, File] = False):
        """

        :param file_path:
        :param additional_files:
        :param env:
        """

        raw = self._parse_to_string(file_path=file_path, additional_files=additional_files)

        environment = Environment()
        parsed = self._render(raw, environment)
        config = yaml.load(parsed, Loader=yaml.SafeLoader)
        self._config = config

    def create(self, key: str) -> Any:
        """
        Creates the object specified by the supplied key.

        :param key: The key from the supplied config files that corresponds to the object you want to create.
        :type key: str
        :return:
        """

        config = self._config[key]
        if "class_name" in config:
            return self._create_object(config)
        else:
            raise RuntimeError

    @classmethod
    def _create_object(cls, config: dict) -> Any:
        module_name = config.pop("module")
        module = importlib.import_module(module_name)
        class_name = config.pop("class_name")
        klass = getattr(module, class_name)

        kwargs = dict()
        for key, value in config.items():
            if isinstance(value, str):
                if hasattr(builtins, value):
                    kwargs[key] = getattr(builtins, value)
                else:
                    kwargs[key] = value
            elif isinstance(value, list):
                value = [cls._create_object(v) for v in value]
                kwargs[key] = value
            elif isinstance(value, dict):
                if "module" in value:
                    kwargs[key] = cls._create_object(value)
                elif _type_ in value:
                    module = value.get(_module_, builtins)
                    parser = getattr(module, value[_type_])
                    parsed = parser(value[_value_])
                    kwargs[key] = parsed
                else:
                    kwargs[key] = value
            else:
                kwargs[key] = value

        obj = klass(**kwargs)
        return obj

    @staticmethod
    def _parse_to_string(file_path: File, additional_files: Optional[Files]) -> str:
        """
        Parse the config file, and any additional config files, into a buffer.
        :param file_path:
        :param additional_files:
        :return:
        """
        buffer = io.StringIO()
        file_paths = _list_of_files(additional_files)
        file_paths.append(file_path)
        for file_path in file_paths:
            with open(file_path, "r") as fh:
                buffer.write(fh.read())

        buffer.seek(0)
        return buffer.read()

    @staticmethod
    def _render(raw: str, environment) -> str:
        """
        Render the raw template string.

        :param raw:
        :param environment:
        :return:
        """
        template = Template(raw)
        rendered = template.render(**environment)
        return rendered


if __name__ == "__main__":
    pass
