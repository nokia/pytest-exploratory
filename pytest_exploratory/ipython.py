"""Integration with IPython/Jupyter."""

import atexit
import shlex
from tempfile import TemporaryDirectory
from IPython.core.magic import Magics, magics_class, line_magic
from IPython.core.error import UsageError
from typing import Optional, Callable, Any
import warnings
from pytest_exploratory.interactive import InteractiveSession


sphinxify: Optional[Callable[[Any], Any]]
try:
    import docrepr.sphinxify as sphx

    def sphinxify(doc):
        with TemporaryDirectory() as dirname:
            return {
                'text/html': sphx.sphinxify(doc, dirname),
                'text/plain': doc
            }
except ImportError:
    sphinxify = None


config = None
# HACK for pytest
magics = None


@magics_class
class PytestMagics(Magics):
    """IPython magics to control a pytest test session."""
    # TODO have smart autocompletion

    def __init__(self, shell):
        global magics
        super().__init__(shell)
        self.shell = shell
        self._session = InteractiveSession()
        self._in_pytest = False
        if config is not None:
            self._session.config = config
            self._in_pytest = True
        magics = self

    @line_magic
    def pytest_session(self, data):
        """Start a pytest session.

        This sets the ``pytest_session`` variable to an :class:`.interactive.InteractiveSession` instance.
        """
        if data == "":
            args = None
        else:
            args = shlex.split(data)
        self._session.start(args)
        self._session.session_start()
        self.shell.push({"pytest_session": self._session})

    @line_magic
    def pytest_context(self, context):
        """Get into the given pytest context.

        If the context is a full test name, the fixtures are setup and put into corresponding variables.
        """
        context = context.strip()
        variables = self._session.context(context)
        self.shell.push(variables)

    @line_magic
    def pytest_contextinfo(self, level):
        """Show information about the current test context (currently just code).

        Pass a number to show information about a parent context.
        """
        if level == "":
            level = 0
        else:
            level = int(level)
        docformat = sphinxify if self.shell.sphinxify_docstring else None
        context_item = self._session.context_item
        for _ in range(level):
            context_item = context_item.parent
        self.shell.inspector.pinfo(context_item.obj, detail_level=2, formatter=docformat)

    @line_magic
    def pytest_fixture(self, fixturenames):
        """Load the given fixture(s) and add them to the variables.

        For parametrized fixtures, you can give the parameter id between brackets, e.g. ``fixture_name[param_id]``.
        """
        for fixturename in fixturenames.split():
            name, value = self._session.fixture_with_name(fixturename)
            self.shell.push({name: value})

    @line_magic
    def pytest_fixtureinfo(self, fixturename):
        """Show information about the fixture.

        E.g.: ``%pytest_fixtureinfo tmpdir``
        """
        fixturename = fixturename.strip()
        try:
            definition = self._session.fixture_definition(fixturename)
        except KeyError:
            print(f"No fixture named {fixturename}")
            return
        docformat = sphinxify if self.shell.sphinxify_docstring else None
        self.shell.inspector.pinfo(definition.func, formatter=docformat)

    @line_magic
    def pytest_fixtureinfodetail(self, fixturename):
        """Show detailed information about the fixture.

        E.g.: ``%pytest_fixtureinfodetail tmpdir``
        """
        fixturename = fixturename.strip()
        try:
            definition = self._session.fixture_definition(fixturename)
        except KeyError:
            print(f"No fixture named {fixturename}")
            return
        docformat = sphinxify if self.shell.sphinxify_docstring else None
        self.shell.inspector.pinfo(definition.func, detail_level=2, formatter=docformat)

    def pytest_fixture_completer(self, ipython, event):
        return self._session.fixturenames

    @line_magic
    def pytest_runtests(self, line=""):
        """Run the tests in the current context."""
        with self._session.temporary_pdb(self.shell.call_pdb):
            try:
                self._session.runtests(shlex.split(line))
            except SystemExit:
                pass

    def _try_pytest_session_stop(self):
        if self._session.session is None:
            return
        self._session.session_stop()
        if not self._in_pytest:
            self._session.stop()

    def shutdown_hook(self):
        self._try_pytest_session_stop()

    @line_magic
    def pytest_session_stop(self, data=""):
        """Stop the pytest session.

        This ensures that all fixtures are torn down.
        """
        if self._session.session is None:
            raise UsageError("Pytest session not started")
        self._try_pytest_session_stop()


def _shell_initialized(ipython):
    # TODO remove this when it's fixed in IPython
    warnings.filterwarnings('ignore', module=r'^jedi\.cache')


def load_ipython_extension(ipython):
    console = PytestMagics(ipython)
    ipython.register_magics(console)
    atexit.register(console.shutdown_hook)
    ipython.set_hook('complete_command', console.pytest_fixture_completer, re_key='%pytest_fixture')
    # TODO autocomplete for pytest_context
    ipython.events.register('shell_initialized', _shell_initialized)


def unload_ipython_extension(ipython):
    pass
