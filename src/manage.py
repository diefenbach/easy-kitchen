#!/usr/bin/env python
"""Django's command-line utility for this project."""

import os
import sys


def main():
    """Run a Django management command; uses the development settings unless DJANGO_SETTINGS_MODULE is
    set.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.development")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
