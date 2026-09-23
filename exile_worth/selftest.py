"""Start-up check of a build, without the interface: `ExileWorth.exe --self-test out.json`.

A packaged build can start and still miss a data file (RapidOCR's models, the
catalogue, the tab icons) that only fails once a stash is read. This loads each
of them, reads a drawn number with the real OCR, and exits non-zero on any failure.
"""
import json
import sys
import traceback


def checks():
    import cv2
    import numpy as np

    def catalogue():
        from .catalog import reference_items
        count = len(reference_items())
        assert count > 100, count
        return count

    def tab_icons():
        from .app import TAB_ICONS
        count = len(list(TAB_ICONS.glob('*.png')))
        assert count >= 5, count
        return count

    def tab_symbol():
        from .vision import symbol_reference
        shape = symbol_reference('top').shape
        return list(shape)

    def ocr():
        from .vision import DigitReader
        image = np.zeros((120, 320, 3), np.uint8)
        cv2.putText(image, '1234', (50, 85), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 4)
        result, _elapsed = DigitReader().ocr(image)
        text = ''.join(line[1] for line in result or [])
        assert '1234' in text, text
        return text

    def interface():
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        version = root.tk.call('info', 'patchlevel')
        root.destroy()
        return version

    def data_folder():
        from .model import DATA
        return str(DATA)

    return dict(catalogue=catalogue, tab_icons=tab_icons, tab_symbol=tab_symbol,
                ocr=ocr, interface=interface, data_folder=data_folder)


def run(report=None):
    from . import __version__
    results, ok = {'version': __version__, 'frozen': bool(getattr(sys, 'frozen', False))}, True
    for name, check in checks().items():
        try:
            results[name] = {'ok': True, 'value': check()}
        except Exception:
            ok = False
            results[name] = {'ok': False, 'error': traceback.format_exc()}
    text = json.dumps(results, indent=2, ensure_ascii=False)
    if report:
        with open(report, 'w', encoding='utf-8') as file:
            file.write(text)
    elif sys.stdout:
        print(text)
    return 0 if ok else 1
