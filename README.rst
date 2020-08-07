pytest-exploratory
==================

Control a pytest session interactively from IPython for exploratory testing.

For more details, `see the documentation <https://pytest-exploratory.readthedocs.io/en/latest/>`_.

Installation
------------

The extension is available on `PyPI <https://pypi.org/project/pytest-exploratory/>`_ and depends on IPython and pytest::

    pip install pytest-exploratory

Usage
-----

To load the extension, add ``pytest_exploratory.ipython`` to the IPython extension list, e.g. in ``.ipython/profile_default/ipython_config.py``::

    c.InteractiveShellApp.extensions = ['pytest_exploratory.ipython']

Or load it from IPython itself::

    In [1]: %load_ext pytest_exploratory.ipython

It adds some `magics <https://ipython.readthedocs.io/en/stable/interactive/tutorial.html#magic-functions>`_ to use pytest from the REPL (see also :class:`pytest_exploratory.ipython.PytestMagics`)::

    In [1]: # Put yourself in a specific pytest context
       ...: # (optional, it defaults to a "session" context)
    In [2]: %pytest_context tests/my_test/test_something.py
    ...
    In [3]: # Request fixture(s)
    In [4]: %pytest_fixture my_fixture other_fixture
    ...
    In [5]: my_fixture
    Out[5]: 'value'
    In [6]: # Run the tests in the current context
    In [7]: %pytest_runtests
    ...
    In [8]: # Explicitly end and teardown the test session
       ...: # (automatically done on exit)
    In [9]: %pytest_session_stop
    ...

You can directly get the setup of a test::

    In [1]: %pytest_context tests/my_test/test_something.py::test_case
    ...
        SETUP    M test_case_fixture (fixtures used: dependency)
    In [2]: my_fixture
    Out[2]: 'value'
    In [3]: %pytest_runtests
    tests/my_test/test_something.py::test_case
    ...

It checks your test file for changes and reloads the code if it's edited between test runs::

    In [1]: %pytest_context tests/test_mytest.py
    ...
    In [2]: %pytest_runtests
    ...
    In [3]: # Test before edit
    ...
    In [4]: !nano tests/test_mytest.py
    ...
    In [5]: %pytest_runtests
    ...
    # Test after edit
    ...

Arguments can be passed to pytest with the ``%pytest_session`` magic::

    In [1]: %pytest_session -v
    ...

Some extra magics help navigating the test code/documentation::

    In [1]: # Show the test code
    In [2]: %pytest_contextinfo
    ...
    In [3]: # Show the module/class code
    In [4]: %pytest_contextinfo 1
    ...
    In [5]: # Fixture documentation
    In [6]: %pytest_fixtureinfo my_fixture
    ...
    In [7]: # Fixture code
    In [8]: %pytest_fixtureinfodetail my_fixture
    ...


License
-------

This project is licensed under the MIT license - see the `LICENSE <https://github.com/nokia/pytest-exploratory/blob/master/LICENSE>`_.