import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['--self-test']:
        from .selftest import run
        return run(argv[1] if len(argv) > 1 else None)

    from .capture import enable_dpi_awareness

    enable_dpi_awareness()

    from .model import migrate_legacy_data

    migrate_legacy_data()

    from .app import App

    App().mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
