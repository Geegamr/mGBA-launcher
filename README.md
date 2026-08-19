mGBA Launcher
=============

The Logo used for the app is trademarked or copyrighted by mGBA and they own all the rights for it

=============

A small tile-based GUI launcher for mGBA ROMs built with tkinter and Pillow.

Features

- Tile grid of ROMs with large icons
- Auto-matching icons (exact, normalized, fuzzy)
- Toggle show/hide titles
- Dark and Light themes
- Image decoding via Pillow (PNG/JPEG/GIF)
- Placeholder icon generation when needed

Planned features

- Favorites (star + filter)
- Search bar
- Sort by name and additional sort options

Requirements

- Python 3.8+ (3.14 tested)
- Pillow (`pip install Pillow`)
- Optional: PyInstaller for building the exe

Run from source

1. Ensure dependencies are installed:

```powershell
python -m pip install --user Pillow
```

1. Run the app directly:

```powershell
python ".\mGBA launcher\mGBA_Launcher.py"
```

Build a one-file Windows executable (PyInstaller)

1. Install PyInstaller if needed:

```powershell
python -m pip install --user pyinstaller
```

1. Build (from the project folder):

```powershell
python -m PyInstaller --onefile --windowed --add-data "placeholder.png;." mGBA_Launcher.py
```

Notes

- Config is stored at `%APPDATA%\\mGBA launcher\\config.json`.
- If an icon doesn't match, rename the icon file to match the ROM stem or place it in the icons folder.
- The built exe is placed in `dist\mGBA_Launcher.exe` by PyInstaller.
