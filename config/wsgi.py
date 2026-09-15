"""
WSGI config — only used by tooling that requires WSGI; the live server runs ASGI.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
