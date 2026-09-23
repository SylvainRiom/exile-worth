"""`settings.json` in the data folder: small user preferences, merged key by key.

A missing, damaged or read-only file never prevents the app from starting:
reads fall back to an empty dict and a failed write keeps the session value.
"""
from __future__ import annotations

import json
from pathlib import Path

from .model import DATA


def settings_file(directory=None):
    return Path(directory or DATA) / 'settings.json'


def read(directory=None):
    try:
        data = json.loads(settings_file(directory).read_text('utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write(directory=None, **values):
    """Merge `values` into the file; other keys are kept. False if not written."""
    file = settings_file(directory)
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        data = read(directory) | values
        temporary = file.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), 'utf-8')
        temporary.replace(file)
        return True
    except OSError:
        return False
