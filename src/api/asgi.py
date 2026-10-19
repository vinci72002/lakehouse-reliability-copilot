"""ASGI entry point.

Run with ``uvicorn api.asgi:app``. Importing this module builds the
default in-memory incidents and is intentionally separate from the
application factory used by tests.
"""

from api.app import create_app

app = create_app()
