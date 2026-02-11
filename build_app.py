#!/usr/bin/env python3
import shutil
import subprocess
import sys
import os

def build():
    # 1. Clean previous builds
    print("Clean build directories...")
    if os.path.exists("build"):
        shutil.rmtree("build", ignore_errors=True)
    if os.path.exists("dist"):
        shutil.rmtree("dist", ignore_errors=True)

    # 3. Run py2app (Alias Mode for <10MB size)
    print("Running setup.py py2app -A (Alias Mode)...")
    try:
        subprocess.check_call([sys.executable, "setup.py", "py2app", "-A"])
        
        # In Alias Mode, we don't need manual library injection because
        # it uses the system/conda environment directly.
        
        print("\nBuild successful! App is in ./dist/Service Manager.app")
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with exit code {e.returncode}")
        sys.exit(e.returncode)

if __name__ == "__main__":
    build()
