# PyInstaller build of Exile Worth, one folder (not one file: a one-file build
# unpacks itself on every start, which is slow and alarms antivirus software).
#   .\.venv311\Scripts\pyinstaller.exe --noconfirm packaging\exile_worth.spec
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / 'exile_worth'
VERSION = re.search(r"__version__ = '([^']+)'", (PACKAGE / '__init__.py').read_text('utf-8'))[1]
numbers = tuple(int(part) for part in VERSION.split('.')) + (0,) * (4 - VERSION.count('.') - 1)

datas = [
    (str(PACKAGE / 'item_catalog.json'), 'exile_worth'),
    (str(PACKAGE / 'assets'), 'exile_worth/assets'),
    (str(PACKAGE / 'reference_tabs'), 'exile_worth/reference_tabs'),
    # config.yaml and the three .onnx models RapidOCR loads relative to itself.
    *collect_data_files('rapidocr_onnxruntime'),
]

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('ProductName', 'Exile Worth'),
            StringStruct('FileDescription', 'Exile Worth'),
            StringStruct('FileVersion', VERSION),
            StringStruct('ProductVersion', VERSION),
            StringStruct('OriginalFilename', 'ExileWorth.exe'),
        ])]),
        VarFileInfo([VarStruct('Translation', [0x0409, 1200])]),
    ])

a = Analysis(
    [str(ROOT / 'packaging' / 'launch.py')],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=collect_submodules('rapidocr_onnxruntime'),
    excludes=['matplotlib', 'pandas', 'scipy', 'IPython', 'pytest'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='ExileWorth',
    console=False,
    icon=str(PACKAGE / 'assets' / 'app.ico'),
    version=version_info,
)
coll = COLLECT(exe, a.binaries, a.datas, name='ExileWorth')
