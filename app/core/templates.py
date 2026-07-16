"""Jinja2 template rendering.

A single shared ``templates`` object so the directory is configured in one
place and templates are parsed once rather than per request.
"""

from fastapi.templating import Jinja2Templates

from app.core.config import BASE_DIR

TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"

templates = Jinja2Templates(directory=TEMPLATES_DIR)
