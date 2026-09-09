#!/usr/bin/env python
"""Entrée du nouveau projet uniquement. Le manage.py racine reste legacy."""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
