"""Production entry point: `waitress-serve --port=$PORT wsgi:app`."""

from server.app import app, warm_caches

warm_caches()
