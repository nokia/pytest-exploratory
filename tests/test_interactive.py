import pytest
from pytest_exploratory.interactive import InteractiveSession


@pytest.fixture
def session():
    session = InteractiveSession()
    yield session
    session.session_stop()
    session.stop()


def test_simple_interactive_session(testdir, session):
    testdir.makepyfile("""
        import pytest
        @pytest.fixture()
        def afix():
            return 10
        @pytest.fixture()
        def errorfixture():
            raise Exception('Error in fixture')
        def test_empty():
            print('debug')
        def test_withfix(afix):
            assert 0 == 1
        def test_failfixture(errorfixture):
            pass
        class TestClass:
            @pytest.fixture(scope="class")
            def class_fixture(self):
                return 10
            def test_class_test(self, class_fixture):
                pass
    """)
    session.start()
    session.session_start()
    session.collect("test_simple_interactive_session.py")
    session.context("test_simple_interactive_session.py::test_empty")
    session.fixture('afix')
    with pytest.raises(Exception):
        session.fixture('errorfixture')
    session.runtests()
    fixtures = session.context("test_simple_interactive_session.py::TestClass::test_class_test")
    assert "class_fixture" in fixtures
    assert fixtures["class_fixture"] == 10
    assert session.fixture('class_fixture') == 10


def test_params(testdir, session):
    testdir.makepyfile("""
        import pytest
        @pytest.fixture(
            params=[1, 2],
            ids=["a", "b"]
        )
        def param(request):
            return request.param
        @pytest.fixture(
            params=[5, 6],
        )
        def paramint(request):
            return request.param
        def test_withparam(param):
            pass
    """)
    session.context("test_params.py")
    session.fixture_definition("param")
    session.fixture_param("param", "b")
    assert session.fixture("param") == 2
    for name in("param", "param[a]", "param[b]"):
        assert name in session.fixturenames
    session.context("test_params.py")
    assert session.fixture_with_name("param[a]") == ("param", 1)
    assert session.fixture("param[b]") == 2
    assert session.fixture("paramint[5]") == 5


def test_autouse_params(testdir, session):
    testdir.makepyfile("""
        import pytest
        @pytest.fixture(
            params=[1, 2],
            autouse=True,
        )
        def param(request):
            return request.param
        @pytest.fixture(
            params=["test1", "test2"],
            autouse=True,
            scope="module",
        )
        def param2(request):
            return request.param
        def test_withparam(param):
            pass
    """)
    session.context("test_autouse_params.py[test1-2]")
    assert session.fixture("param") == 2
    assert session.fixture("param2") == "test1"


def test_outside_root(testdir, tmp_path, session):
    testdir.makepyfile("""
        def test_empty():
            pass
    """)
    tmp_pytest = tmp_path / 'test_something.py'
    tmp_pytest.write_text("""
import pytest
@pytest.fixture
def my_fixture():
    return 1
def test_something():
    pass
""")
    session.context(str(tmp_pytest))
    assert session.fixture("my_fixture") == 1
    session.runtests()


def test_no_context(testdir, session):
    request = session.fixture("request")
    assert request is not None
