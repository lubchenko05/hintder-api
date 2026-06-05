"""Business logic — pure orchestration over storages and services.

Functions here never import FastAPI. They take a ``DBStorage`` (and any
services) plus plain arguments, enforce invariants, and raise ``AppException``
subclasses on failure. This keeps them callable from views, tasks, and scripts.
"""
