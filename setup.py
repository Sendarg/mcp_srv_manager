"""
Setup script for building macOS .app bundle.

Usage:
    python setup.py py2app
"""

from setuptools import setup

APP = ["main.py"]
DATA_FILES = ["services.json", "icon.png"]
OPTIONS = {
    "argv_emulation": False,
    "packages": ["customtkinter", "PIL"],
    "includes": ["customtkinter", "PIL", "packaging"],
    "excludes": [
        "pip", "setuptools", "wheel", 
        "numpy", "pandas", "scipy", "matplotlib", 
        "sphinx", "ipython", "notebook",
        "docutils", "jedi"
    ],
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

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
