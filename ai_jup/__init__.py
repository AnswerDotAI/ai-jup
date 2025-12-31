"""AI-powered Jupyter Lab extension with prompt cells."""
try:
    from ._version import __version__
except ImportError:
    __version__ = "0.1.0"

from .handlers import setup_handlers


def _jupyter_labextension_paths():
    return [{"src": "labextension", "dest": "ai-jup"}]


def _jupyter_server_extension_points():
    return [{"module": "ai_jup"}]


def _load_jupyter_server_extension(server_app):
    """Registers the API handler to receive HTTP requests from the frontend extension."""
    setup_handlers(server_app.web_app)
    name = "ai_jup"
    server_app.log.info(f"Registered {name} server extension")
