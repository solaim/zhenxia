"""Task-local progress shared by async adapters without changing engine APIs."""
from contextvars import ContextVar

reporter = ContextVar('download_progress', default=None)


def report(**values):
    callback = reporter.get()
    if callback:
        callback(values)
