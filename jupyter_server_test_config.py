"""Jupyter server configuration for Galata E2E tests."""
from jupyterlab.galata import configure_jupyter_server

configure_jupyter_server(c)

# Additional settings for testing
c.ServerApp.token = ''
c.ServerApp.password = ''
c.ServerApp.disable_check_xsrf = True
c.ServerApp.open_browser = False
c.LabApp.expose_app_in_browser = True
