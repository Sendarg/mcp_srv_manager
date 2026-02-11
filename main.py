#!/usr/bin/env python3
"""
MCP Service Manager GUI
A simple cross-platform GUI for managing background services.
"""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

# Redirect stdout/stderr removed for cleanup
# Ensure environment is set up correctly

try:
    if getattr(sys, "frozen", False):
        # FIX: Load User's Shell PATH
        try:
            # Use zsh login shell to get the real PATH
            user_path = subprocess.check_output(
                ["/bin/zsh", "-l", "-c", "echo $PATH"], 
                text=True
            ).strip()
            os.environ["PATH"] = user_path
        except Exception:
            pass
            
        # Append current python bin and common paths
        current_py_bin = os.path.dirname(sys.executable)
        common_paths = [
            current_py_bin,
            "/opt/homebrew/bin",
            "/usr/local/bin",
            os.path.expanduser("~/bin")
        ]
        
        current_path = os.environ.get("PATH", "")
        for p in common_paths:
            if p not in current_path and os.path.exists(p):
                current_path = f"{p}:{current_path}"
        os.environ["PATH"] = current_path

except Exception:
    pass

except Exception:
    pass  # Worst case: silent fail, but don't crash the import



import customtkinter as ctk

# --- Configuration ---
# Config file path is determined below using _get_resource_path

# --- Theme ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Constants
COLOR_BG = "#1e1e1e"
COLOR_BG_CARD = "#2b2b2b"
COLOR_BG_ERR = "#451e1e"
COLOR_TEXT = "#ffffff"
COLOR_TEXT_DIM = "#a0a0a0"
COLOR_RUNNING = "#4ade80"  # Green-400
COLOR_STOPPED = "#f87171"  # Red-400
COLOR_BTN_HOVER = "#3f3f46"
COLOR_BORDER = "#444444"

# Environment
SHELL_ENV = os.environ.copy()
# Sanitize environment for subprocesses to avoid bundle leakage
for key in ["PYTHONPATH", "PYTHONHOME", "DYLD_LIBRARY_PATH"]:
    SHELL_ENV.pop(key, None)

# Add common paths to PATH in SHELL_ENV just in case
# (Previous fix updated os.environ, so SHELL_ENV.copy() should have it, but consistent ordering helps)
SHELL_ENV["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")

def _get_resource_path(relative_path: str) -> Path:
    """Get absolute path to resource, works for dev and for PyInstaller/py2app."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # py2app sets sys.frozen, but resources are in Contents/Resources
        if getattr(sys, "frozen", False):
            base = os.environ.get("RESOURCEPATH")
            if base:
                base_path = base
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

    return Path(base_path) / relative_path



# --- Configuration ---
CONFIG_FILE = _get_resource_path("services.json")


class ServiceManager:
    """Backend: manages service processes."""

    def __init__(self):
        self.services: list[dict] = []
        self.processes: dict[str, subprocess.Popen] = {}
        self.errors: dict[str, str] = {}
        self.load_config()

    def load_config(self):
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                self.services = data.get("services", [])
        else:
            self.services = []

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"services": self.services}, f, indent=2, ensure_ascii=False)

    def add_service(self, name: str, command: str) -> dict:
        svc = {"name": name, "command": command}
        self.services.append(svc)
        self.save_config()
        return svc

    def update_command(self, index: int, new_command: str):
        if 0 <= index < len(self.services):
            self.services[index]["command"] = new_command
            self.save_config()

    def remove_service(self, index: int):
        if 0 <= index < len(self.services):
            svc = self.services[index]
            self.stop(svc["name"])
            self.services.pop(index)
            self.save_config()

    @staticmethod
    def _extract_port(command: str) -> int | None:
        """Parse --port=XXXX or --port XXXX or -p XXXX from a command."""
        m = re.search(r'(?:--port[=\s]|-p\s)(\d+)', command)
        return int(m.group(1)) if m else None

    @staticmethod
    def _check_port_conflict(port: int) -> str | None:
        """Check if port is in use. Returns 'PID/process_name' or None."""
        try:
            result = subprocess.run(
                ["lsof", "-i", f":{port}", "-t", "-sTCP:LISTEN"],
                capture_output=True, text=True, timeout=3
            )
            pids = result.stdout.strip().splitlines()
            if not pids:
                return None
            # Get process name for the first PID
            infos = []
            for pid in pids[:3]:  # show up to 3
                try:
                    ps = subprocess.run(
                        ["ps", "-p", pid, "-o", "comm="],
                        capture_output=True, text=True, timeout=2
                    )
                    pname = ps.stdout.strip().split('/')[-1] or "?"
                    infos.append(f"{pid}({pname})")
                except Exception:
                    infos.append(pid)
            return ", ".join(infos)
        except Exception:
            return None

    @staticmethod
    def _find_same_cmd_processes(command: str) -> str | None:
        """Find existing processes running this exact command."""
        try:
            # Safe search: look for unique part of command (the script/exe name)
            parts = command.strip().split()
            if not parts: return None
            
            # Find the most distinctive part (usually the script path or executable)
            target = parts[0]
            if target.endswith("python") or target.endswith("python3"):
                if len(parts) > 1:
                    target = parts[1] # Use the script name instead
            
            target_name = target.split('/')[-1]

            result = subprocess.run(
                ["ps", "-eo", "pid,command"],
                capture_output=True, text=True, timeout=2
            )
            lines = result.stdout.strip().splitlines()
            infos = []
            my_pid = os.getpid()
            
            for line in lines[1:]: # Skip header
                p = line.strip().split(None, 1)
                if len(p) < 2: continue
                pid_str, cmd_line = p[0], p[1]
                
                if pid_str == str(my_pid): continue
                if "grep" in cmd_line or " pgrep " in cmd_line: continue
                if "main.py" in cmd_line and "mcp_srv_manager" in cmd_line: continue

                # Check if it looks like the target
                if target in cmd_line or (target_name and target_name in cmd_line):
                     # Double check it's not just a substring match of something else
                     infos.append(f"{pid_str}")

            return ", ".join(infos[:3]) if infos else None

        except Exception:
            return None

    def start(self, name: str) -> bool:
        if name in self.processes and self.processes[name].poll() is None:
            return True

        svc = self._find(name)
        if not svc:
            self.errors[name] = "Service not found"
            return False

        self.errors.pop(name, None)

        # 1. Check port
        port = self._extract_port(svc["command"])
        if port:
            blocker = self._check_port_conflict(port)
            if blocker:
                self.errors[name] = f"Port {port} used by {blocker}"
                return False

        # 2. Check existing process with same command
        existing = self._find_same_cmd_processes(svc["command"])
        if existing:
             self.errors[name] = f"Process running: PID {existing}"
             return False

        try:
            import tempfile
            shell = os.environ.get("SHELL", "/bin/zsh")
            escaped_cmd = svc["command"].replace("'", "'\\''")
            wrapped_cmd = f"{shell} -l -c '{escaped_cmd}'"

            # Capture stderr to a temp file for error diagnostics
            stderr_file = tempfile.NamedTemporaryFile(
                mode='w+', suffix='.err', delete=False, prefix='svcmgr_'
            )
            proc = subprocess.Popen(
                wrapped_cmd,
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
                env=SHELL_ENV,
                preexec_fn=os.setsid if sys.platform != "win32" else None,
            )
            time.sleep(0.8)
            if proc.poll() is not None:
                # Read captured stderr
                stderr_file.seek(0)
                stderr_out = stderr_file.read().strip()[:200]
                stderr_file.close()
                try:
                    os.unlink(stderr_file.name)
                except Exception:
                    pass

                err_msg = f"Exit code {proc.returncode}"
                if stderr_out:
                    err_msg += f" — {stderr_out}"
                if port:
                    blocker = self._check_port_conflict(port)
                    if blocker:
                        err_msg += f" | port {port} held by PID {blocker}"
                # Check for existing same-command processes
                existing = self._find_same_cmd_processes(svc["command"])
                if existing:
                    err_msg += f" | running: {existing}"
                self.errors[name] = err_msg
                return False
            stderr_file.close()
            try:
                os.unlink(stderr_file.name)
            except Exception:
                pass

            self.processes[name] = proc
            return True
        except Exception as e:
            self.errors[name] = str(e)
            return False

    def stop(self, name: str) -> bool:
        self.errors.pop(name, None)
        proc = self.processes.get(name)
        if proc is None:
            return True
        if proc.poll() is not None:
            self.processes.pop(name, None)
            return True

        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if sys.platform == "win32":
                    proc.kill()
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=3)
            except Exception:
                pass
        except ProcessLookupError:
            pass
        except Exception as e:
            self.errors[name] = str(e)
            return False
        finally:
            self.processes.pop(name, None)
        return True

    def restart(self, name: str) -> bool:
        self.stop(name)
        time.sleep(0.3)
        return self.start(name)

    def is_running(self, name: str) -> bool:
        proc = self.processes.get(name)
        if proc is None:
            return False
        if proc.poll() is not None:
            self.processes.pop(name, None)
            return False
        return True

    def get_pid(self, name: str) -> int | None:
        proc = self.processes.get(name)
        if proc and proc.poll() is None:
            return proc.pid
        return None

    def get_error(self, name: str) -> str | None:
        return self.errors.get(name)

    def _find(self, name: str) -> dict | None:
        for svc in self.services:
            if svc["name"] == name:
                return svc
        return None

    def stop_all(self):
        for name in list(self.processes.keys()):
            self.stop(name)


class App(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("Service Manager")
        self.geometry("820x420")
        self.minsize(700, 280)

        # Set window icon
        try:
            from PIL import Image, ImageTk
            icon_path = _get_resource_path("icon.png")
            if icon_path.exists():
                img = Image.open(icon_path).resize((256, 256))
                self._icon_img = ImageTk.PhotoImage(img)
                self.wm_iconphoto(True, self._icon_img)
        except Exception:
            pass

        self.mgr = ServiceManager()
        self._rebuilding = False
        self._pending_rebuild = False
        self._build_ui()
        self._rebuild_list()
        self._auto_refresh()
        self.after(10, self._center_window)

    def _center_window(self):
        """Center window on screen."""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        # Shift up a bit (visual center)
        y = (self.winfo_screenheight() // 2) - (height // 2) - 50
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Title
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        ctk.CTkLabel(
            title_frame, text="⚙  Service Manager",
            font=("Arial", 18, "bold"), text_color=COLOR_TEXT
        ).pack(side="left")

        # Service list
        self.scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0
        )
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=0)

        # Add service bar
        add_frame = ctk.CTkFrame(self, fg_color=COLOR_BG_CARD, corner_radius=10)
        add_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 14))
        add_frame.grid_columnconfigure(1, weight=1)

        self.entry_name = ctk.CTkEntry(
            add_frame, width=90, placeholder_text="Name", font=("Arial", 12)
        )
        self.entry_name.grid(row=0, column=0, padx=(12, 4), pady=10)

        self.entry_cmd = ctk.CTkEntry(
            add_frame, placeholder_text="Command, e.g. talkito --mcp-server --port=8000",
            font=("Menlo", 12)
        )
        self.entry_cmd.grid(row=0, column=1, padx=4, pady=10, sticky="ew")

        ctk.CTkButton(
            add_frame, text="+ Add", width=64, height=30, corner_radius=8,
            fg_color="#7c3aed", hover_color="#6d28d9",
            font=("Arial", 13, "bold"), command=self._on_add
        ).grid(row=0, column=2, padx=(6, 12), pady=10)

    # ---- List management ----

    def _rebuild_list(self):
        """Full rebuild of the service row list."""
        if self._rebuilding:
            self._pending_rebuild = True
            return
        self._rebuilding = True

        try:
            for widget in self.scroll_frame.winfo_children():
                widget.destroy()

            services = list(self.mgr.services)  # snapshot

            if not services:
                ctk.CTkLabel(
                    self.scroll_frame,
                    text="No services yet.  Add one below ↓",
                    font=("Arial", 13), text_color=COLOR_TEXT_DIM,
                ).pack(pady=40)
                return

            for i, svc in enumerate(services):
                name = svc["name"]
                running = self.mgr.is_running(name)
                pid = self.mgr.get_pid(name)
                error = self.mgr.get_error(name)
                self._create_row(i, svc, running, pid, error)
        finally:
            self._rebuilding = False
            if self._pending_rebuild:
                self._pending_rebuild = False
                self.after(50, self._rebuild_list)

    def _create_row(self, index: int, svc: dict, running: bool,
                    pid: int | None, error: str | None):
        """Create one service row frame — vertical container."""
        # Main container for the item
        bg = COLOR_BG_ERR if error else COLOR_BG_CARD
        item_frame = ctk.CTkFrame(self.scroll_frame, fg_color=bg, corner_radius=6)
        item_frame.pack(fill="x", pady=1)

        # -- Top Row: Status, Info, Controls --
        top_row = ctk.CTkFrame(item_frame, fg_color="transparent")
        top_row.pack(fill="x", pady=2, padx=4)

        # Status dot
        color = COLOR_RUNNING if running else COLOR_STOPPED
        ctk.CTkLabel(
            top_row, text="●", font=("Arial", 12), text_color=color, width=14
        ).pack(side="left", padx=(4, 2), pady=6)

        # PID
        pid_text = str(pid) if pid else "—"
        pid_color = COLOR_TEXT_DIM if pid else COLOR_BORDER
        ctk.CTkLabel(
            top_row, text=pid_text, font=("Menlo", 9),
            text_color=pid_color, width=44, anchor="e"
        ).pack(side="left", padx=(0, 2), pady=6)

        # Name
        ctk.CTkLabel(
            top_row, text=svc["name"], font=("Arial", 12, "bold"),
            text_color=COLOR_TEXT, anchor="w", width=80
        ).pack(side="left", padx=(4, 4), pady=6)

        # Command field
        cmd_entry = ctk.CTkEntry(
            top_row, font=("Menlo", 11), text_color=COLOR_TEXT_DIM,
            fg_color="transparent", border_width=0, height=26
        )
        cmd_entry.insert(0, svc["command"])
        cmd_entry.bind("<FocusOut>", lambda e, i=index: self._on_cmd_change(i, cmd_entry.get()))
        cmd_entry.bind("<Return>", lambda e: self.focus())
        cmd_entry.pack(side="left", fill="x", expand=True, padx=8)

        # Controls
        ctk.CTkButton(
            top_row, text="✕", width=24, height=24, corner_radius=12,
            fg_color="transparent", hover_color="#dc2626",
            text_color=COLOR_TEXT_DIM, font=("Arial", 11),
            command=lambda i=index: self._on_delete(i)
        ).pack(side="right", padx=(2, 4))

        ctk.CTkButton(
            top_row, text="↻", width=28, height=24, corner_radius=5,
            fg_color="#2563eb", hover_color="#1d4ed8",
            font=("Arial", 13),
            command=lambda i=index: self._on_restart(i)
        ).pack(side="right", padx=2)

        switch_var = ctk.BooleanVar(value=running)
        switch = ctk.CTkSwitch(
            top_row, text="", variable=switch_var,
            width=40, height=20,
            progress_color=COLOR_RUNNING,
            button_color=COLOR_TEXT,
            fg_color=COLOR_BORDER,
            # We bind command via configure below to capture cmd_entry
        )
        switch.pack(side="right", padx=(4, 4))

        # Disable cmd if running
        if running:
            cmd_entry.configure(state="disabled")
        else:
            cmd_entry.configure(border_width=1, border_color=COLOR_BORDER)

        # Bind toggle
        switch.configure(command=lambda i=index, v=switch_var, w=cmd_entry: self._on_toggle(i, v.get(), w))


        # -- Error Row: Message & Kill Button --
        if error:
            # Try parsing PID
            conflicting_pid = None
            try:
                import re
                m = re.search(r'(?:PID|running:?|by)\s*(\d+)', error)
                if m: conflicting_pid = int(m.group(1))
            except Exception: pass

            err_row = ctk.CTkFrame(item_frame, fg_color="transparent")
            err_row.pack(fill="x", padx=10, pady=(0, 6))

            ctk.CTkLabel(
                err_row, text=f"⚠️ {error}", font=("Arial", 11),
                text_color=COLOR_STOPPED, anchor="w", wraplength=500
            ).pack(side="left", fill="x", expand=True)

            if conflicting_pid:
                def _do_kill(_pid=conflicting_pid):
                    try:
                        os.kill(_pid, signal.SIGKILL)
                    except Exception as e:
                        print(f"Failed to kill {_pid}: {e}")
                    self.after(200, self._auto_refresh)

                ctk.CTkButton(
                    err_row, text=f"Kill PID {conflicting_pid}", width=80, height=20,
                    fg_color="#b91c1c", hover_color="#991b1b",
                    text_color="#ffffff",
                    font=("Arial", 10, "bold"), command=_do_kill
                ).pack(side="right", padx=5)

    # ---- Actions ----

    def _on_cmd_change(self, index: int, new_cmd: str):
        # Helper to update command from entry
        if 0 <= index < len(self.mgr.services):
            if new_cmd != self.mgr.services[index]["command"]:
                self.mgr.update_command(index, new_cmd)

    def _save_cmd(self, index: int, entry_widget):
         # Legacy wrapper if needed, or just use _on_cmd_change
         self._on_cmd_change(index, entry_widget.get().strip())

    def _on_toggle(self, index: int, turn_on: bool, cmd_widget):
        if not (0 <= index < len(self.mgr.services)):
            return
        # Save any command edit before starting
        if turn_on:
             self._on_cmd_change(index, cmd_widget.get().strip())
        name = self.mgr.services[index]["name"]
        if turn_on:
            threading.Thread(target=self._do_action,
                             args=(self.mgr.start, name), daemon=True).start()
        else:
            threading.Thread(target=self._do_action,
                             args=(self.mgr.stop, name), daemon=True).start()

    def _on_restart(self, index: int):
        if 0 <= index < len(self.mgr.services):
            name = self.mgr.services[index]["name"]
            threading.Thread(target=self._do_action,
                             args=(self.mgr.restart, name), daemon=True).start()

    def _do_action(self, fn, name: str):
        fn(name)
        self.after(100, self._rebuild_list)

    def _on_delete(self, index: int):
        if 0 <= index < len(self.mgr.services):
            self.mgr.remove_service(index)
            self._rebuild_list()

    def _on_add(self):
        name = self.entry_name.get().strip()
        cmd = self.entry_cmd.get().strip()
        if not name or not cmd:
            return
        self.mgr.add_service(name, cmd)
        self.entry_name.delete(0, "end")
        self.entry_cmd.delete(0, "end")
        self._rebuild_list()

    def _auto_refresh(self):
        """Lightweight status check — only rebuild if a status actually changed."""
        changed = False
        for svc in self.mgr.services:
            name = svc["name"]
            was_running = name in self.mgr.processes
            is_running = self.mgr.is_running(name)
            if was_running and not is_running:
                changed = True
        if changed:
            self._rebuild_list()
        self.after(2000, self._auto_refresh)

    def destroy(self):
        self.mgr.stop_all()
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
