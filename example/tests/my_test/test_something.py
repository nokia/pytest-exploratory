import pytest


@pytest.fixture(scope="module")
def my_fixture():
    return "value"


@pytest.fixture()
def other_fixture():
    return 1


def test_case(my_fixture):
    assert my_fixture == "value"


def test_fail(my_fixture):
    assert my_fixture == "other"
