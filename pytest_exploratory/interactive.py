"""Run a pytest session interactively."""

import sys
import inspect
import logging
from pathlib import Path
import tempfile
from importlib import reload
import re
import warnings
import pytest
import argparse
import shlex
from contextlib import contextmanager
from _pytest.config import _prepareconfig
from _pytest.main import Session
from _pytest.python import CallSpec2, Metafunc, FunctionDefinition
from _pytest.mark import ParameterSet
import _pytest.debugging


LOGGER = logging.getLogger(__name__)


def request_teardown(request, fixturename):
    """Teardown a given fixture name."""
    # HACK
    fixturedef = request._get_active_fixturedef(fixturename)
    fixturedef.finish(request)
    try:
        del request._fixture_defs[fixturename]
    except (KeyError, AttributeError):
        pass
    try:
        del request._arg2fixturedefs[fixturename]
    except (KeyError, AttributeError):
        pass
    try:
        del request._arg2index[fixturename]
    except (KeyError, AttributeError):
        pass
    try:
        del request._fixture_values[fixturename]
    except (KeyError, AttributeError):
        pass


def _is_child(item, nodeid):
    while item is not None:
        if item.nodeid == nodeid:
            return True
        item = item.parent
    return False

class _FilterCollection:
    def __init__(self, root, path=""):
        self.root = root
        self.path = path

    def pytest_ignore_collect(self, path, config):
        # Not really correct
        path = str(path)[len(self.root) + 1:]
        if path.startswith(self.path):
            return
        if self.path.startswith(path):
            return
        return True


def _reload_items(items):
    for item in items:
        try:
            obj = item._getobj()
        except (AttributeError, TypeError):
            continue
        if not inspect.ismethod(obj):
            continue
        if not hasattr(obj, "__self__"):
            continue
        obj_self = obj.__self__
        try:
            mod = sys.modules[obj_self.__class__.__module__]
        except KeyError:
            continue
        if not hasattr(mod, obj_self.__class__.__name__):
            continue
        cls = getattr(mod, obj_self.__class__.__name__)
        setattr(obj_self.__class__, obj.__name__, getattr(cls, obj.__name__))


class InteractiveSession:
    """Wrapper around pytest to collect and run tests interactively.

    Not working very well yet, pytest does not like to run or collect tests multiple times.
    It needs to be better integrated with pytest's core.
    """
    # TODO this is a state machine, would be good to have proper transition checks

    def __init__(self):
        self.config = None
        self.session = None
        self.context_node = None
        self.context_item = None
        self._request = None
        self._mtime = None
        self._fixturenames = None

    def _teardown_if_needed(self, item, nextitem):
        try:
            self.session._setupstate.teardown_exact(item, nextitem)
        except AssertionError:
            pass

    def start(self, args=None):
        """Initialize the pytest config from the given arguments."""
        if self.config is None:
            if args is None:
                args = ['-s']
            if '-s' not in args:
                args = ['-s'] + list(args)
            if '--disable-pytest-warnings' not in args:
                args = ['--disable-pytest-warnings'] + list(args)
            self.config = _prepareconfig(args, None)
        self._config_override()
        self._filter = _FilterCollection(str(self.config.rootdir))
        self.config.pluginmanager.register(self._filter, "interactive_filter")

    def _config_override(self):
        # Overriding some options which don't make sense in interactive use
        self.config.option.continue_on_collection_errors = True
        # Might be useful
        # config.pluginmanager._duplicatepaths.clear()
        try:
            self.config.option.keepduplicates = True
        except AttributeError:
            pass

    def session_start(self):
        """Start a pytest session."""
        if self.config is None:
            self.start()
        self.config._do_configure()
        if hasattr(Session, "from_config"):
            self.session = Session.from_config(self.config)
        else:  # TODO remove with pytest >= 5.4
            self.session = Session(self.config)
        self.config.hook.pytest_sessionstart(session=self.session)
        # TODO remove this when it's fixed in IPython
        warnings.filterwarnings('ignore', module=r'^jedi\.cache')

    def collect(self, path):
        """Collect tests under the given path."""
        if self.session is None:
            self.session_start()
        nodeid = path
        if "::" in nodeid:
            path = nodeid.split("::", 1)[0]
        self._filter.path = path
        # Pytest discovers tests outside of the root through arguments
        try:
            (Path(self.config.rootdir) / Path(path)).relative_to(Path(self.config.rootdir))
            is_in_root = True
        except ValueError:
            is_in_root = False
        if not is_in_root:
            self.config.args.append(path)
        try:
            self.config.hook.pytest_collection(session=self.session)
        finally:
            if not is_in_root:
                self.config.args.pop()
        # TODO filter this in plugin?
        items = list(self.session.items)
        if nodeid != path:
            items = [item for item in items if _is_child(item, nodeid)]
        return items

    def _dummy_item(self, item, context_param=""):
        # TODO support class methods
        def dummy(request):
            pass
        fixtureinfo = self.session._fixturemanager.getfixtureinfo(item, dummy, cls=None)
        if hasattr(pytest.Function, "from_parent"):
            func = pytest.Function.from_parent(
                item,
                name="dummy",
                callobj=dummy,
                fixtureinfo=fixtureinfo,
            )
        else:  # TODO remove with pytest >= 5.4
            func = pytest.Function(
                name="dummy",
                parent=item,
                callobj=dummy,
                fixtureinfo=fixtureinfo,
            )
        if hasattr(FunctionDefinition, "from_parent"):
            definition = FunctionDefinition.from_parent(
                item,
                name="dummy",
                callobj=dummy,
            )
        else:  # TODO remove with pytest >= 5.4
            definition = FunctionDefinition(
                name="dummy",
                parent=item,
                callobj=dummy,
            )
        metafunc = Metafunc(
            definition,
            fixtureinfo,
            self.config,
            cls=None,
            module=item.getparent(pytest.Module).obj,
        )
        func.callspec = CallSpec2(metafunc)
        self.config.hook.pytest_generate_tests(metafunc=metafunc)
        if context_param != "":
            for callspec in metafunc._calls:
                if callspec.id == context_param:
                    if hasattr(pytest.Function, "from_parent"):
                        return pytest.Function.from_parent(
                            item,
                            name=f"{func.name}[{context_param}]",
                            callspec=callspec,
                            callobj=dummy,
                            fixtureinfo=fixtureinfo,
                            keywords={callspec.id: True},
                            originalname=func.name,
                        )
                    else:  # TODO remove with pytest >= 5.4
                        return pytest.Function(
                            name=f"{func.name}[{context_param}]",
                            parent=item,
                            callspec=callspec,
                            callobj=dummy,
                            fixtureinfo=fixtureinfo,
                            keywords={callspec.id: True},
                            originalname=func.name,
                        )
            suggestions = [callspec.id for callspec in metafunc._calls]
            raise ValueError(
                f"Could not find context parametrization {context_param}, possible values: {suggestions}"
            )
        return func

    def _dummy_context(self):
        # HACK it would make more sense to create a dummy node
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test_dummy.py'
            path.write_text("""
def test_exists():
    pass
""")
            return self.context(str(path))

    def context(self, context=""):
        """Put ourselves in the given context (for fixture and conftest discovery)."""
        self._fixturenames = None
        if self.session is None:
            self.session_start()
        if context == "":
            return self._dummy_context()
        item = None
        root = self.session.config.rootpath.resolve()
        cwd = Path.cwd().resolve()
        try:
            prefix = f"{root.relative_to(cwd)}/"
        except ValueError:
            prefix = ""
        if prefix and context.startswith(prefix):
            context = context[len(prefix):]
        # TODO parse the context to better handle parametrization
        # TODO find the right item as a tree traversal from the root instead
        for item in getattr(self.session, 'items', []):
            if item.nodeid.startswith(context):
                break
        if item is None or not item.nodeid.startswith(context):
            if '::' in context:
                fspath, _ = context.split('::', 1)
            else:
                if '[' in context:
                    fspath, _ = context.split('[', 1)
                else:
                    fspath = context
            self.collect(fspath)
        for item in getattr(self.session, 'items', []):
            if item.nodeid.startswith(context):
                break
        if item is None:
            raise Exception(
                f"Unknown context {context}, "
                f"make sure it exists, starts with test_, and it contains a test."
            )
        self.context_node = item
        if not context.endswith(item.nodeid):
            if '[' in context:
                param_index = context.find('[')
                context_param = context[param_index + 1:-1]
                context = context[:param_index]
            else:
                context_param = ""
            while not context.endswith(item.nodeid):
                item = item.parent
            if isinstance(item, Session):
                raise Exception(
                    f"Unknown context {context}"
                )
            self.context_node = item
            item = self._dummy_item(item, context_param)
        if self.context_item is not None:
            self._teardown_if_needed(self.context_item, item)
        self.context_item = item
        if hasattr(item, "_request") and isinstance(item._request, bool):
            item._initrequest()
        self.config.hook.pytest_runtest_setup(item=item, when="setup")
        self._request = self.context_item._request
        fixtures = {}
        extra_fixtures = []
        if inspect.ismethod(self._request.node.obj):
            extra_fixtures.append("self")
        for fixturename in (*self._request.fixturenames, *extra_fixtures):
            try:
                fixtures[fixturename] = self.fixture(fixturename)
            except Exception:
                LOGGER.exception("Could not get fixture %s", fixturename)
        return fixtures

    def _reload(self):
        reloaded = False
        # TODO is it possible to reload the fixtures/fixture code?
        if self.context_item is None:
            return reloaded
        module = self.context_item
        while not isinstance(module, pytest.Module):
            if module is None:
                return reloaded
            module = module.parent
        if module.fspath is None:
            return
        path = Path(str(module.fspath))
        mtime = path.stat().st_mtime
        if self._mtime is not None and mtime > self._mtime:
            reload(module.obj)
            reloaded = True
        self._mtime = mtime
        item = self.context_item
        while item is not None:
            if isinstance(item, pytest.Function) and getattr(item, "name", "") == "dummy":
                item = item.parent
                continue
            try:
                delattr(item, "_obj")
            except (AttributeError, TypeError):
                pass
            item = item.parent
        return reloaded

    def _relative_name(self, item):
        abs_part = self.context_node.nodeid
        if not item.nodeid.startswith(abs_part):
            raise Exception(f"Item {item.nodeid} is not relative to {abs_part}")
        relative = item.nodeid[len(abs_part):]
        # TODO better way to remove the separator
        relative = relative.lstrip("/:")
        return relative

    def runtests(self, args=tuple()):
        """Run the tests under the current context."""
        parser = argparse.ArgumentParser(
            prog='pytest_runtests',
            description='Run tests under the current context'
        )
        parser.add_argument('tests',
                            nargs='*',
                            metavar="TEST",
                            default=tuple(),
                            help='Test names to run, relative to the current context')
        parser.add_argument('-k',
                            metavar="EXPRESSION",
                            default=None,
                            help='only run tests which match the given substring expression')
        parser.add_argument('-m',
                            metavar="MARKEXPR",
                            default=None,
                            help='only run tests matching given mark expression')
        if isinstance(args, str):
            args = shlex.split(args)
        arguments = parser.parse_args(args)
        restore_keyword = []
        restore_markexpr = []
        if arguments.k:
            restore_keyword.append(self.config.option.keyword)
            self.config.option.keyword = arguments.k
        if arguments.m:
            restore_markexpr.append(self.config.option.markexpr)
            self.config.option.markexpr = arguments.m
        try:
            self._runtests(arguments.tests)
        finally:
            if restore_markexpr:
                self.config.option.markexpr = restore_markexpr[0]
            if restore_keyword:
                self.config.option.keyword = restore_keyword[0]

    def _runtests(self, testnames):
        reloaded = self._reload()
        if self.context_item is self.context_node:
            items = [self.context_item]
            lastitem = self._dummy_item(self.context_item.parent)
        else:
            items = self.collect(self.context_node.nodeid)
            lastitem = self.context_item
        if testnames:
            # TODO better match on separator
            regex = re.compile("(" + ("|".join(re.escape(name) for name in testnames)) + r")(/|::|\[|$)")
            new_items = []
            for item in items:
                if regex.match(self._relative_name(item)):
                    new_items.append(item)
            items[:] = new_items
        if reloaded:
            _reload_items(items)
        if items:
            self._teardown_if_needed(lastitem, items[0])
        for i, item in enumerate(items):
            nextitem = items[i + 1] if i + 1 < len(items) else lastitem
            self.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
        self.config.hook.pytest_terminal_summary(
            terminalreporter=self.config.pluginmanager.get_plugin('terminalreporter'),
            exitstatus=0,
            config=self.config,
        )
        # Clear the reports so they do not constantly show up
        self.config.pluginmanager.get_plugin('terminalreporter').stats.clear()

    def fixture(self, fixturename):
        """Return the value of the given fixture."""
        _, value = self.fixture_with_name(fixturename)
        return value

    def fixture_with_name(self, fixturename):
        """Return the name and value of the given fixture."""
        if fixturename == "self":
            value = getattr(self._request.node.obj, "__self__", None)
            if value is not None:
                return "self", value
        if "[" in fixturename:
            fixturename, param = fixturename[:-1].split("[")
            self.fixture_param(fixturename, param)
        return fixturename, self.request.getfixturevalue(fixturename)

    def fixture_definition(self, fixturename):
        if self.session is None:
            raise KeyError("Pytest session not started")
        return self.session._fixturemanager._arg2fixturedefs[fixturename][-1]

    def _fixture_ids(self, fixturename):
        fixturedef = self.fixture_definition(fixturename)
        metafunc = self.context_item._pyfuncitem.callspec.metafunc

        # TODO figure out how to avoid using internal things
        try:
            argnames, parameters = ParameterSet._for_parametrize(
                fixturedef.argname,
                fixturedef.params,
                metafunc.function,
                self.config,
                function_definition=metafunc.definition,
            )
        except TypeError:
            argnames, parameters = ParameterSet._for_parametrize(
                fixturedef.argname,
                fixturedef.params,
                metafunc.function,
                self.config,
                nodeid=self.context_item.nodeid,
            )
        try:
            ids = metafunc._resolve_arg_ids(
                argnames,
                fixturedef.ids,
                parameters,
                item=self.context_item,
            )
        except TypeError:
            ids = metafunc._resolve_arg_ids(
                argnames,
                fixturedef.ids,
                parameters,
                nodeid=self.context_item.nodeid,
            )
        return ids

    def fixture_param(self, fixturename, param):
        """Choose parameter for this parametrized fixture."""
        fixturedef = self.fixture_definition(fixturename)
        ids = self._fixture_ids(fixturename)
        value = fixturedef.params[ids.index(param)]
        callspec = self.context_item._pyfuncitem.callspec
        if fixturename in callspec.params and hasattr(fixturedef, "cached_result"):
            # Fixture already setup, first cleanup fixture
            request_teardown(self.request, fixturename)
        callspec.params[fixturename] = value
        if hasattr(callspec, "indices"):
            callspec.indices[fixturename] = ids.index(param)

    @property
    def fixturenames(self):
        if self.session is None:
            return tuple()
        fixturenames = []
        if self._fixturenames is None:
            for name, fdef in self.session._fixturemanager._arg2fixturedefs.items():
                fdef = fdef[-1]
                fixturenames.append(name)
                if fdef.params:
                    for paramid in self._fixture_ids(name):
                        fixturenames.append(f"{name}[{paramid}]")
            self._fixturenames = tuple(fixturenames)
        return self._fixturenames

    @property
    def request(self):
        """Request fixture for the current context."""
        if self.context_item is None:
            self.context()
        return self._request

    def session_stop(self):
        """Stop the test session (runs teardown)."""
        # FIXME why is it in a bad state in the first place?
        setupstate = self.session._setupstate
        to_delete = []
        for colitem in setupstate._finalizers:
            if colitem not in setupstate.stack:
                to_delete.append(colitem)
        for colitem in reversed(to_delete):
            del setupstate._finalizers[colitem]
        self.session.startdir.chdir()
        self.config.hook.pytest_sessionfinish(session=self.session, exitstatus=0)
        self.session = None

    def stop(self):
        """Stop pytest."""
        self.config._ensure_unconfigure()
        self.config = None

    @contextmanager
    def temporary_pdb(self, usepdb=True):
        """Temporarily enable pdb."""
        if not usepdb:
            yield
            return
        if self.config is None:
            yield
            return
        # Relying too much on pytest internals...
        pdbinvoke = self.config.pluginmanager.get_plugin("pdbinvoke")
        if pdbinvoke:
            # Plugin already there
            yield
            return
        old_usepdb = self.config.option.usepdb
        self.config.option.usepdb = True
        try:
            _pytest.debugging.pytest_configure(self.config)
            cleanup = self.config._cleanup.pop()
            try:
                yield
            finally:
                cleanup()
                self.config.pluginmanager.unregister(
                    self.config.pluginmanager.get_plugin("pdbinvoke")
                )
        finally:
            self.config.option.usepdb = old_usepdb
