import os
import sys

from django.core.management import execute_from_command_line


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "xsignal_django.settings")
    execute_from_command_line(["manage.py", "runserver", "0.0.0.0:8050", *sys.argv[1:]])


if __name__ == "__main__":
    main()
