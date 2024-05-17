"""
WSGI config for staadease project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

from dotenv import load_dotenv

from pathlib import Path

load_dotenv(dotenv_path=Path.cwd() / '.env') # path is projects root-dir. or base-dir.

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'staadease.settings')

application = get_wsgi_application()
