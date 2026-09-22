"""Isolated PostgreSQL test database; run with --settings=config.settings.test_postgres."""
from django.core.exceptions import ImproperlyConfigured

from .base import *

if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Set DB_ENGINE=postgres for PostgreSQL tests.")

DATABASES["default"]["TEST"] = {"NAME": "test_lider_lead_management"}
