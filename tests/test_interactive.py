import pytest
import os
from pytest_exploratory.interactive import InteractiveSession


@pytest.fixture
def session(testdir):
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
        def test_empty_fail():
            assert False
        def test_withfix(afix):
            assert 0 == 1
        def test_failfixture(errorfixture):
            pass
        class TestClass:
            def method(self):
                return 1
            @pytest.fixture(scope="class")
            def class_fixture(self):
                return 10
            def test_class_test(self, class_fixture):
                pass
    """)
    session.start()
    session.session_start()
    with pytest.raises(Exception):
        # Shoud fail, but next collect should work
        session.context("test_does_not_exist.py")
    session.context("test_simple_interactive_session.py")
    session.collect("test_simple_interactive_session.py")
    session.runtests()
    assert session.session.testsfailed == 3
    session.session.testsfailed = 0
    session.runtests(["test_empty", "test_failfixture"])
    assert session.session.testsfailed == 1
    session.session.testsfailed = 0
    session.context("test_simple_interactive_session.py::test_empty")
    session.fixture('afix')
    with pytest.raises(Exception):
        session.fixture('errorfixture')
    session.runtests()
    assert session.session.testsfailed == 0
    fixtures = session.context("test_simple_interactive_session.py::TestClass::test_class_test")
    assert "class_fixture" in fixtures
    assert fixtures["class_fixture"] == 10
    assert session.fixture('class_fixture') == 10
    assert "self" in fixtures
    fixtures["self"].method() == 1


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


def test_change_context(testdir, session):
    testdir.makepyfile(
        """
        def test_something():
            pass
        """,
        test_other="""
        def test_other():
            pass
        """,
    )
    session.context("test_change_context.py")
    session.context("test_other.py")


def test_class(testdir, session):
    testdir.makepyfile("""
import pytest


@pytest.fixture()
def fix1():
    pass


@pytest.fixture()
def fix2():
    pass


def test_case(fix1, fix2):
    pass

class TestClass:
    def test_case(self, fix1, fix2):
        pass
    """)
    session.start()
    session.session_start()
    session.context("test_class.py")
    session.runtests()
    assert session.session.testsfailed == 0
    session.runtests()
    assert session.session.testsfailed == 0


def test_dir(testdir, session):
    r = testdir.mkpydir("atest")
    suite = r.mkdir("suite")
    suite.join("__init__.py").write("")
    suite.join("test_something.py").write("""
import pytest

@pytest.fixture()
def fixture():
    return 1

def test_x(fixture):
    assert fixture == 1
""")
    session.start()
    session.session_start()
    session.context("atest/suite/test_something.py")
    session.runtests()
    assert session.session.testsfailed == 0


def test_reload(testdir, session):
    testdir.makepyfile("""
class TestClass:
    def test_case(self):
        assert 1 == 1
    """)
    session.start()
    session.session_start()
    session.context("test_reload.py::TestClass::test_case")
    session.runtests()
    assert session.session.testsfailed == 0
    testdir.makepyfile("""
class TestClass:
    def test_case(self):
        assert 1 == 2
    """)
    # TODO better way to detect changes
    stat = os.stat("test_reload.py")
    os.utime("test_reload.py", times=(stat.st_atime + 2, stat.st_mtime + 2))
    session.runtests()
    assert session.session.testsfailed == 1


def test_reload_function(testdir, session):
    testdir.makepyfile(test_reload="""
def test_case():
    assert 1 == 1
    """)
    session.start()
    session.session_start()
    session.context("test_reload.py::test_case")
    session.runtests()
    assert session.session.testsfailed == 0
    testdir.makepyfile(test_reload="""
def test_case():
    assert 1 == 2
    """)
    # TODO better way to detect changes
    stat = os.stat("test_reload.py")
    os.utime("test_reload.py", times=(stat.st_atime + 2, stat.st_mtime + 2))
    session.runtests()
    assert session.session.testsfailed == 1

def test_runtest_parse(testdir, session):
    testdir.makepyfile("""
        import pytest

        def test_basic1():
            assert 1 == 1

        def test_basic2():
            assert 1 == 1

        def test_inter1():
            assert 1 == 1

        def test_inter2():
            assert 1 == 2
                       """)
    session.start()
    session.session_start()
    session.context("test_runtest_parse.py")
    session.runtests("-k basic")
    assert session.session.testsfailed == 0
    assert session.session.testscollected == 2
    session.runtests("-k inter")
    assert session.session.testscollected == 2
    assert session.session.testsfailed == 1
    testdir.makepyfile("""
        import pytest
        @pytest.mark.basic
        def test_1():
            assert 1 == 1

        def test_2():
            assert 1 == 4

        @pytest.mark.inter
        def test_3():
            assert 1 == 3

        @pytest.mark.inter
        @pytest.mark.basic
        def test_inter2():
            assert 1 == 2
                       """)
    session.context("test_runtest_parse.py")
    session.runtests("-m basic")
    assert session.session.testsfailed == 2
    session.runtests("-m 'basic and inter'")
    assert session.session.testscollected == 1
    assert session.session.testsfailed == 3
    session.runtests("-m 'inter and not basic'")
    assert session.session.testscollected == 1
    assert session.session.testsfailed == 4
    session.runtests("test_2")
    assert session.session.testsfailed == 5

