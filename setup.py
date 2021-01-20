from setuptools import setup

test_requirements = ['pytest']

setup(
    name='pytest_exploratory',
    version='0.3',
    description='Interactive console for pytest.',
    url='https://github.com/nokia/pytest-exploratory',
    author='Iwan Briquemont',
    author_email='iwan.briquemont@nokia.com',
    license='MIT',
    packages=['pytest_exploratory'],
    install_requires=['py>=1.1.1', 'pytest>=5.3', 'ipython'],
    tests_require=test_requirements,
    extras_require={'test': test_requirements},
    package_data={
        'pytest_exploratory': ['py.typed'],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Pytest",
        "Framework :: IPython",
        "Framework :: Jupyter",
        "Topic :: Software Development :: Testing",
    ],
    python_requires='>=3.6',
)
