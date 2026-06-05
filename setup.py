"""Editable-install shim so ``pip install -e .`` exposes the ``dating`` package."""

from setuptools import find_packages, setup

setup(
    name="dating-api",
    version="0.0.0",
    packages=find_packages(exclude=("tests", "tests.*")),
    python_requires=">=3.12",
)
