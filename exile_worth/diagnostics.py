"""Session log for recognition failures.

The hard part of this project is diagnosing *why* a stash was not recognised.
Layout scores, icon runners-up and matcher metrics are already computed on every
frame; without this module they are discarded and a failure report leaves nothing
to read. Everything here is local: the log never leaves the machine.

Levels
    INFO   lifecycle and every *decision change* (layout, tab identity, coverage)
    DEBUG  per-cell detail and per-frame metrics, enabled with EXILE_LOG_LEVEL=DEBUG

INFO is deliberately change-triggered: the live loop runs three times a second
and an unconditional line per frame would bury the moment things went wrong.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import traceback
from pathlib import Path

from .model import DATA

log = logging.getLogger('exile_worth')

_configured = False


def setup(directory=None, level=None):
    """Attach a rotating file handler once. A read-only data dir is not fatal."""
    global _configured
    if _configured:
        return log
    level = level or os.getenv('EXILE_LOG_LEVEL', 'INFO').upper()
    log.setLevel(getattr(logging, level, logging.INFO))
    log.propagate = False
    try:
        path = Path(directory or DATA) / 'session.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)-5s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        log.addHandler(handler)
    except OSError:
        # Logging must never prevent the application from running.
        log.addHandler(logging.NullHandler())
    _configured = True
    return log


def failure(context, exc):
    """Record the traceback. Callers still show their own short message."""
    log.error('%s: %s\n%s', context, exc,
              ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip())


class ChangeGate:
    """Let a repeating event through only when its payload changes.

    The live loop re-derives the same verdict on every frame. Logging each one
    would make the file unreadable and hide the transition that matters.
    """
    def __init__(self):
        self.seen = {}

    def passes(self, key, value):
        if self.seen.get(key) == value:
            return False
        self.seen[key] = value
        return True

    def reset(self):
        self.seen.clear()


def format_scores(scores, limit=4):
    """`[(score, name), …]` as a compact, sorted, readable ranking."""
    ranked = sorted(scores, reverse=True)[:limit]
    return ', '.join(f'{name}={score:.3f}' for score, name in ranked)
