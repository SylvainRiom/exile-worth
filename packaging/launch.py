"""Entry script of the packaged build: the same start-up as `python -m exile_worth`."""
import sys

from exile_worth.__main__ import main

sys.exit(main())
