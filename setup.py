"""
Setup script for building macOS .app bundle.

Usage:
    Development (alias mode, fast, symlinks to source):
        python setup.py py2app -A

    Production (standalone bundle):
        python setup.py py2app
"""

import sys
from setuptools import setup

APP = ["main.py"]
DATA_FILES = ["services.json", "icon.png"]

# Detect alias mode from command line
alias_mode = "-A" in sys.argv or "--alias" in sys.argv

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "icon.icns",
    "plist": {
        "CFBundleName": "Service Manager",
        "CFBundleDisplayName": "Service Manager",
        "CFBundleIdentifier": "com.local.servicemanager",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "LSMinimumSystemVersion": "10.15",
    },
}

# Only set packages/includes/excludes for standalone builds.
# Alias mode uses symlinks and doesn't need them.
if not alias_mode:
    OPTIONS.update({
        "packages": ["customtkinter", "PIL"],
        "includes": ["customtkinter", "PIL", "packaging"],
        "excludes": [
            "pip", "setuptools", "wheel",
            "numpy", "pandas", "scipy", "matplotlib",
            "sphinx", "ipython", "notebook",
            "docutils", "jedi"
        ],
    })

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
