# MCP Service Manager

A lightweight macOS GUI for managing background services and MCP servers.

![Screenshot](screenshot.png)

## Features

- Start / Stop / Restart services with one click
- Real-time status indicators and PID tracking
- Live port detection for running processes
- Port conflict detection with one-click kill
- Duplicate process detection
- Inline command editing with undo/redo
- Auto-detects shell environment (Homebrew, Conda, etc.)
- Dark theme UI built with CustomTkinter

## Requirements

- Python 3.10+
- macOS (tested on Sequoia)

## Quick Start

```bash
git clone https://github.com/Sendarg/mcp_srv_manager.git
cd mcp_srv_manager
pip install -r requirements.txt
python main.py
```

## Build macOS App

```bash
python build_app.py
```

Builds in alias mode — creates a small `.app` bundle in `dist/` that uses your system Python.

## Configuration

Add services via the GUI, or edit `services.json` directly.  
See `services.json.example` for the format.

## License

MIT
