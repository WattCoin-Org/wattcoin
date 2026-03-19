# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all data files for GUI frameworks
datas = []
datas += collect_data_files('tkinter')
datas += collect_data_files('PIL')
datas += collect_data_files('PyQt5', include_py_files=True) if 'PyQt5' in sys.modules else []
datas += collect_data_files('PyQt6', include_py_files=True) if 'PyQt6' in sys.modules else []
datas += collect_data_files('PySide2', include_py_files=True) if 'PySide2' in sys.modules else []
datas += collect_data_files('PySide6', include_py_files=True) if 'PySide6' in sys.modules else []

# Add SSL certificates
datas += [('/etc/ssl/certs', 'ssl/certs')]

# Collect hidden imports
hiddenimports = []
hiddenimports += collect_submodules('tkinter')
hiddenimports += collect_submodules('PIL')
hiddenimports += collect_submodules('requests')
hiddenimports += collect_submodules('urllib3')
hiddenimports += collect_submodules('certifi')
hiddenimports += collect_submodules('ssl')
hiddenimports += collect_submodules('json')
hiddenimports += collect_submodules('threading')
hiddenimports += collect_submodules('queue')
hiddenimports += collect_submodules('logging')
hiddenimports += collect_submodules('datetime')
hiddenimports += collect_submodules('os')
hiddenimports += collect_submodules('sys')
hiddenimports += collect_submodules('platform')
hiddenimports += collect_submodules('subprocess')
hiddenimports += collect_submodules('time')

# GUI framework specific imports
if 'PyQt5' in sys.modules:
    hiddenimports += collect_submodules('PyQt5')
    hiddenimports += ['PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'PyQt5.sip']
if 'PyQt6' in sys.modules:
    hiddenimports += collect_submodules('PyQt6')
    hiddenimports += ['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets']
if 'PySide2' in sys.modules:
    hiddenimports += collect_submodules('PySide2')
    hiddenimports += ['PySide2.QtCore', 'PySide2.QtGui', 'PySide2.QtWidgets']
if 'PySide6' in sys.modules:
    hiddenimports += collect_submodules('PySide6')
    hiddenimports += ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets']

# Blockchain and mining related imports
hiddenimports += [
    'hashlib',
    'socket',
    'select',
    'errno',
    'fcntl',
    'struct',
    'array',
    'binascii',
    'base64',
    'urllib.parse',
    'urllib.request',
    'http.client',
    'http.server',
    'email.mime',
    'email.encoders',
    'mimetypes',
    'tempfile',
    'shutil',
    'glob',
    'fnmatch',
    'pathlib',
    'configparser',
    'argparse',
    'getpass',
    'pwd',
    'grp',
]

# X11 and display related imports for Linux GUI
hiddenimports += [
    '_tkinter',
    'tkinter.ttk',
    'tkinter.font',
    'tkinter.messagebox',
    'tkinter.filedialog',
    'tkinter.colorchooser',
    'tkinter.simpledialog',
]

# Crypto and security imports
hiddenimports += [
    'cryptography',
    'cryptography.hazmat',
    'cryptography.hazmat.primitives',
    'cryptography.hazmat.backends',
    'cryptography.hazmat.backends.openssl',
    'Crypto',
    'Crypto.Cipher',
    'Crypto.Hash',
    'Crypto.PublicKey',
    'Crypto.Signature',
    'Crypto.Random',
]

a = Analysis(
    ['../src/wattnode_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'spyder',
        'anaconda',
        'conda',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='wattnode',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/wattnode.ico' if os.path.exists('../assets/wattnode.ico') else None,
)