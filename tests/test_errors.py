__author__ = "Rohan B. Dalton"

from sygaldry.errors import SygaldryError


def test_error_formats_message_with_context():
    """
    GIVEN: An error with file and config path context.
    WHEN:  Formatting the error as a string.
    THEN:  Both context fields are included.
    """
    err = SygaldryError("boom", file_path="config.yaml", config_path="service.db")

    assert str(err) == "boom (file='config.yaml', path='service.db')"


def test_error_formats_message_without_context():
    """
    GIVEN: An error with no context.
    WHEN:  Formatting the error as a string.
    THEN:  Only the message is shown.
    """
    err = SygaldryError("boom")

    assert str(err) == "boom"


def test_error_args_contains_message():
    """
    GIVEN: An error with a message.
    WHEN:  Accessing its args tuple.
    THEN:  The message is present in args.
    """
    err = SygaldryError("something failed", file_path="f.yaml")

    assert err.args == ("something failed",)


if __name__ == "__main__":
    pass
