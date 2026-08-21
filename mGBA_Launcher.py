#!/usr/bin/env python3
"""
mGBA Launcher
A simple GUI launcher for mGBA ROMs.

Features:
    - Tile-based layout with large icons
    - Toggleable game titles
    - Dark / Light mode
    - Icon matching by ROM filename
    - Placeholder image for ROMs without icons
    - First-run setup wizard (folder selection + theme)
    - Uses mGBA.exe to launch ROMs (supports .gba and .zip)

Requirements: Python 3.x with tkinter, plus Pillow (PIL)
"""

import os
import sys
import json
import struct
import zlib
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import re
import tkinter.font as tkfont
from difflib import SequenceMatcher
from PIL import Image, ImageTk, ImageDraw

# --- Path Configuration ---

_APPDATA = os.environ.get('APPDATA') or os.path.expanduser('~')
CONFIG_DIR = Path(_APPDATA) / 'mGBA launcher'
CONFIG_FILE = CONFIG_DIR / 'config.json'

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
    # When frozen, prefer the placeholder + icon bundled inside the exe (sys._MEIPASS)
    PLACEHOLDER_FILE = Path(getattr(sys, '_MEIPASS', APP_DIR)) / 'placeholder.png'
    ICON_FILE = Path(getattr(sys, '_MEIPASS', APP_DIR)) / 'mGBA_Icon.ico'
else:
    APP_DIR = Path(__file__).parent
    PLACEHOLDER_FILE = APP_DIR / 'placeholder.png'
    ICON_FILE = APP_DIR / 'mGBA_Icon.ico'

ROM_EXTENSIONS = {'.gba', '.zip'}
ICON_EXTENSIONS = ['.png', '.gif', '.jpg', '.jpeg', '.bmp']

# Icon size presets (name -> pixel size)
SIZES = {'small': 96, 'medium': 144, 'large': 192}

# Sort modes (mode key -> display label)
SORT_MODES = {
    'name': 'Name A-Z',
    'name_desc': 'Name Z-A',
    'date_new': 'Newest First',
    'date_old': 'Oldest First',
}

# Theme color palettes (single source of truth)
THEMES = {
    'dark':  {'bg': '#1e1e1e', 'fg': '#e0e0e0', 'card': '#2d2d30',
              'accent': '#007acc', 'tb': '#3c3c3c'},
    'light': {'bg': '#f5f5f5', 'fg': '#202020', 'card': '#ffffff',
              'accent': '#0066cc', 'tb': '#d0d0d0'},
}

# --- Default Configuration ---

DEFAULT_CONFIG = {
    'roms_folder': '',
    'icons_folder': '',
    'mgba_exe': '',
    'theme': 'dark',
    'icon_size': 'small',
    'show_titles': True,
    'sort_mode': 'name',
}

# --- Image Helpers (stdlib only) ---

def create_placeholder_png(path, size=96):
    """Generate a simple placeholder PNG icon using Pillow."""
    try:
        img = Image.new('RGBA', (size, size), (50, 50, 55, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([2, 2, size - 3, size - 3],
                    outline=(110, 110, 120), width=3)
        img.save(path, 'PNG')
    except Exception:
        def _c(t, data):
            crc = struct.pack('>I', zlib.crc32(t + data) & 0xFFFFFFFF)
            return struct.pack('>I', len(data)) + t + data + crc
        raw = bytearray()
        for y in range(size):
            raw.append(0)
            for x in range(size):
                if x < 3 or x >= size - 3 or y < 3 or y >= size - 3:
                    raw.extend((110, 110, 120))
                else:
                    raw.extend((50, 50, 55))
        png = (b'\x89PNG\r\n\x1a\n'
               + _c(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
               + _c(b'IDAT', zlib.compress(bytes(raw)))
               + _c(b'IEND', b''))
        with open(path, 'wb') as f:
            f.write(png)


def load_photoimage(path, max_size=96):
    """Load and resize an image with Pillow; return a PhotoImage or None."""
    try:
        img = Image.open(path)
        img.load()
        img = img.convert('RGBA')
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def normalize_name(name):
    """Normalize a name for matching: lowercase, strip tags and separators."""
    s = str(name).lower()
    s = re.sub(r'\([^)]*\)', ' ', s)               # remove (U), (V1.1), etc.
    s = re.sub(r'\bversion\b', ' ', s)             # remove "version"
    s = re.sub(r'\bthe\b', ' ', s)                 # remove "the"
    s = re.sub(r'[^a-z0-9]+', ' ', s)              # collapse separators
    return ' '.join(s.split())

# --- Configuration Management ---

def load_config():
    """Load config from file, or return None if it doesn't exist."""
    try:
        text = CONFIG_FILE.read_text(encoding='utf-8')
        cfg = json.loads(text)
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_config(cfg):
    """Save config to file, creating the directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=4)


# --- Setup Wizard ---

class SetupWizard(tk.Toplevel):
    """Modal dialog shown on first launch — guides user through setup."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title('mGBA Launcher - First-Time Setup')
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.roms_var = tk.StringVar()
        self.icons_var = tk.StringVar()
        self.mgba_var = tk.StringVar()
        self.theme_var = tk.StringVar(value='dark')
        bg, fg, card, accent = _configure_base_styles(self.theme_var.get())
        self.configure(bg=bg)
        self._build_form()
        self._center_window()
        self.bind('<Escape>', self._on_cancel)

    def _build_form(self):
        pad = {'padx': 10, 'pady': 6}

        # ROMs folder
        frm = ttk.LabelFrame(self, text='ROMs Folder')
        frm.pack(fill='x', **pad)
        row = ttk.Frame(frm)
        row.pack(fill='x', **pad)
        ttk.Entry(row, textvariable=self.roms_var, width=40,
                  state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Browse', command=self._pick_roms).pack(side='left', **pad)

        # Icons folder
        frm = ttk.LabelFrame(self, text='Icons Folder')
        frm.pack(fill='x', **pad)
        row = ttk.Frame(frm)
        row.pack(fill='x', **pad)
        ttk.Entry(row, textvariable=self.icons_var, width=40,
                  state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Browse', command=self._pick_icons).pack(side='left', **pad)

        # mGBA.exe
        frm = ttk.LabelFrame(self, text='mGBA Executable')
        frm.pack(fill='x', **pad)
        row = ttk.Frame(frm)
        row.pack(fill='x', **pad)
        ttk.Entry(row, textvariable=self.mgba_var, width=40,
                  state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Browse', command=self._pick_mgba).pack(side='left', **pad)

        # Theme
        frm = ttk.LabelFrame(self, text='Theme')
        frm.pack(fill='x', **pad)
        row = ttk.Frame(frm)
        row.pack(fill='x', **pad)
        ttk.Radiobutton(row, text='Dark', variable=self.theme_var,
                        value='dark').pack(side='left', **pad)
        ttk.Radiobutton(row, text='Light', variable=self.theme_var,
                        value='light').pack(side='left', **pad)

        # Buttons
        btn_row = ttk.Frame(self)
        btn_row.pack(fill='x', **pad)
        ttk.Button(btn_row, text='Cancel', command=self._on_cancel).pack(side='right', **pad)
        ttk.Button(btn_row, text='OK', command=self._on_ok).pack(side='right', **pad)

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = self.master.winfo_rootx() + self.master.winfo_width() // 2 - w // 2
        y = self.master.winfo_rooty() + self.master.winfo_height() // 2 - h // 2
        self.geometry(f'+{x}+{y}')

    def _pick_roms(self):
        d = filedialog.askdirectory(title='Select ROMs Folder', parent=self)
        if d:
            self.roms_var.set(d)

    def _pick_icons(self):
        d = filedialog.askdirectory(title='Select Icons Folder', parent=self)
        if d:
            self.icons_var.set(d)

    def _pick_mgba(self):
        f = filedialog.askopenfilename(
            title='Select mGBA.exe',
            filetypes=[('Executable files', '*.exe'), ('All files', '*.*')],
            parent=self)
        if f:
            self.mgba_var.set(f)

    def _on_ok(self):
        if not self.roms_var.get() or not self.mgba_var.get():
            messagebox.showwarning('Setup Incomplete',
                                   'ROMs folder and mGBA.exe are required.')
            return
        self.result = {
            'roms_folder': self.roms_var.get(),
            'icons_folder': self.icons_var.get(),
            'mgba_exe': self.mgba_var.get(),
            'theme': self.theme_var.get(),
        }
        self.destroy()

    def _on_cancel(self, event=None):
        self.result = None
        self.destroy()


# --- ROM Tile Widget ---

class RomTile(ttk.Frame):
    """A single tile showing a ROM icon and (optionally) its title."""

    ICON_SIZE = 96  # px

    def __init__(self, parent, rom_name, rom_path, icon_path, show_titles,
                 launch_callback, theme_name='dark'):
        super().__init__(parent, style='Tile.TFrame')
        self.rom_name = rom_name
        self.rom_path = rom_path
        self.icon_path = icon_path
        self.show_titles = show_titles
        self.launch_callback = launch_callback
        self.theme_name = theme_name
        self._photo = None
        self._build()

    def _build(self):
        palette = THEMES[self.theme_name]
        btn_bg = palette['card']
        title_color = palette['fg']

        if self.icon_path and self.icon_path.exists():
            photo = load_photoimage(self.icon_path, max_size=RomTile.ICON_SIZE)
        else:
            if not PLACEHOLDER_FILE.exists():
                create_placeholder_png(PLACEHOLDER_FILE)
            photo = load_photoimage(PLACEHOLDER_FILE, max_size=RomTile.ICON_SIZE)

        if photo is None:
            btn = tk.Button(self, text='[no image]',
                            width=RomTile.ICON_SIZE // 6,
                            height=RomTile.ICON_SIZE // 24,
                            command=self._on_click, bg=btn_bg,
                            highlightthickness=0)
        else:
            self._photo = photo
            btn = tk.Button(self, image=photo,
                            width=RomTile.ICON_SIZE,
                            height=RomTile.ICON_SIZE,
                            command=self._on_click,
                            bd=0, bg=btn_bg,
                            activebackground=btn_bg,
                            cursor='hand2',
                            highlightthickness=0)
        btn.pack(pady=(4, 2))

        # Use themed ttk.Label so foreground/background follow current style
        self.title_label = ttk.Label(
            self, text=self.rom_name, style='Tile.TLabel',
            font=('Segoe UI', 9, 'normal'),
            wraplength=RomTile.ICON_SIZE + 16,
            justify='center')
        self._update_title_visibility()

    def _tile_bg(self):
        return THEMES[self.theme_name]['card']

    def _update_title_visibility(self):
        if self.show_titles.get():
            self.title_label.pack(pady=(2, 4))
        else:
            self.title_label.pack_forget()

    def refresh_theme(self, theme_name):
        """Rebuild the tile with a new theme."""
        self.theme_name = theme_name
        for child in self.winfo_children():
            child.destroy()
        self._build()

    def on_toggle_titles(self):
        self._update_title_visibility()

    def _on_click(self):
        self.launch_callback(self.rom_path)


# --- Theme Helper ---

def _configure_base_styles(theme_name):
    """Apply theme colors to the base ttk widget styles used by dialogs."""
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    palette = THEMES.get(theme_name, THEMES['dark'])
    bg, fg, card, accent, tb = (palette['bg'], palette['fg'],
                                palette['card'], palette['accent'], palette['tb'])
    style.configure('TFrame', background=bg)
    style.configure('TLabel', background=bg, foreground=fg)
    style.configure('TEntry',
                    fieldbackground=card, background=card, foreground=fg,
                    bordercolor=tb, lightcolor=tb, darkcolor=tb)
    style.configure('TLabelFrame', background=bg, foreground=fg)
    style.configure('TButton', background=card, foreground=fg)
    style.map('TButton',
              background=[('active', accent)],
              foreground=[('active', '#ffffff')])
    style.configure('TRadiobutton', background=bg, foreground=fg)
    style.configure('TCheckbutton', background=bg, foreground=fg)
    return bg, fg, card, accent


# --- Main Application ---

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('mGBA Launcher')
        self.root.geometry('800x600')
        self.root.minsize(600, 400)
        try:
            self.root.iconbitmap(str(ICON_FILE))
        except Exception:
            pass

        self.config = load_config()
        # Initialize user preferences from config (with sensible defaults)
        init_show = True
        init_icon = DEFAULT_CONFIG['icon_size']
        if self.config is not None:
            init_show = self.config.get('show_titles', init_show)
            init_icon = self.config.get('icon_size', init_icon)
        self.show_titles = tk.BooleanVar(value=init_show)
        # Current icon pixel size
        self.icon_size = SIZES.get(init_icon, SIZES[DEFAULT_CONFIG['icon_size']])
        self.tile_container = None
        self.tiles = {}
        self._theme_name = 'dark'
        self._canvas = None
        self._vsbar = None
        self._theme_label = None
        self.sort_var = None
        self.config_btn = None
        self._canvas_window = None
        self._canvas_container = None

        if not PLACEHOLDER_FILE.exists():
            create_placeholder_png(PLACEHOLDER_FILE)

    def run(self):
        if self.config is None:
            self._show_setup_wizard()
            if self.config is None:
                sys.exit(0)
        self._setup_ui()
        self._populate_tiles()
        self.root.mainloop()

    # ── Setup Wizard ──
    def _show_setup_wizard(self):
        wizard = SetupWizard(self.root)
        self.root.wait_window(wizard)
        if wizard.result:
            self.config = dict(DEFAULT_CONFIG)
            self.config.update(wizard.result)
            save_config(self.config)

    # ── Theme ──
    def apply_theme(self, theme_name=None):
        if theme_name is None:
            theme_name = self.config.get('theme', 'dark')
        self._theme_name = theme_name
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        bg, fg, card, accent = _configure_base_styles(theme_name)
        self.root.configure(background=bg)
        style.configure('Header.TFrame', background=bg)
        style.configure('Header.TButton', foreground=fg, background=card)
        style.map('Header.TButton',
                  background=[('active', accent)],
                  foreground=[('active', accent)])
        style.configure('Toggle.TButton',
                        foreground=fg, background=card, focusthickness=0)
        style.map('Toggle.TButton',
                  background=[('active', accent)],
                  foreground=[('active', accent)])
        style.configure('Tile.TFrame',
                        background=card, relief='flat', borderwidth=0)
        style.configure('Tile.TLabel', background=card, foreground=fg)
        style.configure('Vertical.TScrollbar',
                        background=card, troughcolor=bg,
                        darkcolor=THEMES[theme_name]['tb'], lightcolor=THEMES[theme_name]['tb'])
        # Combobox/Entry styling for better contrast in light/dark
        try:
            style.configure('TCombobox', fieldbackground=card, background=card, foreground=fg)
            style.map('TCombobox', fieldbackground=[('readonly', card)], foreground=[('readonly', fg)])
            style.configure('TEntry', fieldbackground=card, background=card, foreground=fg)
        except Exception:
            pass
        style.configure('Header.TLabel', background=bg, foreground=fg)
        # Update tk.Menu colors if present
        try:
            if hasattr(self, 'size_menu') and self.size_menu is not None:
                self.size_menu.configure(bg=card, fg=fg,
                                         activebackground=accent,
                                         activeforeground=fg)
        except Exception:
            pass
        try:
            if hasattr(self, 'sort_menu') and self.sort_menu is not None:
                self.sort_menu.configure(bg=card, fg=fg,
                                         activebackground=accent,
                                         activeforeground=fg)
        except Exception:
            pass

    # ── Theme color helpers ──
    def _bg_color(self):
        return THEMES[self._theme_name]['bg']

    def _fg_color(self):
        return THEMES[self._theme_name]['fg']

    def _accent_color(self):
        return THEMES[self._theme_name]['accent']

    def _on_size_change(self, event=None):
        """Handle size dropdown change — rebuild tiles with new icon size."""
        icon_name = self.size_var.get()
        self.config['icon_size'] = icon_name
        self.icon_size = SIZES.get(icon_name, SIZES['small'])
        # Update RomTile class size so rebuilds use the new size
        RomTile.ICON_SIZE = self.icon_size
        # Rebuild all tiles with new size
        for tile in self.tiles.values():
            tile.refresh_theme(self._theme_name)
        self._arrange_tiles()
        # Re-apply scrollregion after rebuild
        self._canvas.configure(scrollregion=self._canvas.bbox('all'))
        # Persist new icon size
        try:
            save_config(self.config)
        except Exception:
            pass

    def _set_size(self, size_name):
        """Helper used by the size menu to set the size and rebuild tiles."""
        try:
            self.size_var.set(size_name)
            # Reuse the main handler to apply changes
            self._on_size_change()
        except Exception:
            pass

    def _on_sort_change(self, mode):
        """Handle sort mode change — re-scan ROMs with new sort order."""
        self.config['sort_mode'] = mode
        if self.sort_var is not None:
            self.sort_var.set(SORT_MODES.get(mode, mode))
        try:
            save_config(self.config)
        except Exception:
            pass
        self._populate_tiles()

    # ── UI Layout ──
    def _setup_ui(self):
        self.apply_theme(self.config.get('theme', 'dark'))

        header = ttk.Frame(self.root, style='Header.TFrame')
        header.pack(fill='x', side='top', padx=8, pady=8)

        # Config button (top-right of header)
        self.config_btn = ttk.Button(header, text='Config',
                                     style='Header.TButton',
                                     command=self._show_config_dialog)
        self.config_btn.pack(side='right', padx=(0, 4))

        ttk.Button(header, text='Toggle Theme',
                    style='Header.TButton',
                    command=self._toggle_theme).pack(side='left', padx=(0, 4))

        # Show/hide titles button - use themed button to match Toggle Theme look
        self.titles_btn = ttk.Button(header, text='Hide Titles',
                                    style='Header.TButton',
                                    command=self._toggle_titles)
        self._update_titles_button()
        self.titles_btn.pack(side='left', padx=(4, 0))

        # Size chooser (styled as a header button)
        size_label = ttk.Label(header, text='Size:', style='Header.TLabel')
        size_label.pack(side='left', padx=(8, 0))
        self.size_var = tk.StringVar(value=self.config.get('icon_size', 'small'))
        size_values = ['small', 'medium', 'large']
        # Use a Menubutton styled as Header.TButton so it matches the toggles
        self.size_menu_btn = ttk.Menubutton(header, textvariable=self.size_var,
                                            style='Header.TButton')
        size_menu = tk.Menu(self.size_menu_btn, tearoff=0,
                    bg=self._bg_color(), fg=self._fg_color(),
                    activebackground=self._accent_color(), activeforeground=self._fg_color())
        for s in size_values:
            size_menu.add_command(label=s, command=lambda s=s: self._set_size(s))
        self.size_menu_btn['menu'] = size_menu
        self.size_menu_btn.pack(side='left', padx=(4, 0))
        self.size_menu = size_menu

        # Sort chooser (styled as a header button, next to size)
        sort_label = ttk.Label(header, text='Sort:', style='Header.TLabel')
        sort_label.pack(side='left', padx=(8, 0))
        self.sort_var = tk.StringVar(value=SORT_MODES.get(self.config.get('sort_mode', 'name'), 'Name A-Z'))
        self.sort_menu_btn = ttk.Menubutton(header, textvariable=self.sort_var,
                                            style='Header.TButton')
        sort_menu = tk.Menu(self.sort_menu_btn, tearoff=0,
                     bg=self._bg_color(), fg=self._fg_color(),
                     activebackground=self._accent_color(), activeforeground=self._fg_color())
        for mode, label in SORT_MODES.items():
            sort_menu.add_command(label=label, command=lambda m=mode: self._on_sort_change(m))
        self.sort_menu_btn['menu'] = sort_menu
        self.sort_menu_btn.pack(side='left', padx=(4, 0))
        self.sort_menu = sort_menu

        # Show/hide titles button (no theme label anymore)

        self._canvas_container = tk.Frame(self.root, bg=self._bg_color())
        self._canvas_container.pack(fill='both', expand=True,
                                    padx=8, pady=8)

        self._canvas = tk.Canvas(self._canvas_container, border=0,
                     highlightthickness=0, bg=self._bg_color())
        self._vsbar = ttk.Scrollbar(self._canvas_container,
                        orient='vertical',
                        command=self._canvas.yview)
        # Configure scrollcommand but don't pack the scrollbar yet; we'll only
        # show it when content exceeds the canvas height.
        self._canvas.configure(yscrollcommand=self._vsbar.set)
        self._canvas.bind_all('<MouseWheel>', self._on_mousewheel)
        self._canvas.pack(side='left', fill='both', expand=True)

        self.tile_container = tk.Frame(self._canvas, bg=self._bg_color())
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self.tile_container, anchor='nw')
        self.tile_container.bind('<Configure>', self._on_frame_configure)
        self._canvas.bind('<Configure>', self._on_canvas_configure)

    def _on_canvas_configure(self, event):
        """Keep the embedded tile container as wide as the canvas."""
        if self._canvas_window is not None:
            self._canvas.itemconfigure(self._canvas_window,
                                       width=event.width)
        self._on_frame_configure(event)

    def _on_frame_configure(self, event):
        self._canvas.configure(scrollregion=self._canvas.bbox('all'))
        self._arrange_tiles()
        # Update visibility of the scrollbar after layout changes
        self._update_scrollbar_visibility()

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(-1 * (event.delta // 120), 'unit')

    def _update_scrollbar_visibility(self):
        """Show the vertical scrollbar only when canvas content exceeds view height."""
        try:
            bbox = self._canvas.bbox('all')
            if bbox:
                content_h = bbox[3] - bbox[1]
            else:
                content_h = 0
            canvas_h = self._canvas.winfo_height()
            # If content is taller than viewport, ensure scrollbar is visible as an overlay
            if content_h > canvas_h + 4:
                # place the scrollbar overlay at the right edge of the canvas container
                if not self._vsbar.winfo_ismapped() and not self._vsbar.winfo_manager():
                    try:
                        self._vsbar.place(in_=self._canvas_container, relx=1.0, x=-6, y=0, anchor='ne', relheight=1.0)
                        self._canvas.configure(yscrollcommand=self._vsbar.set)
                    except Exception:
                        # fallback to pack if place fails
                        self._vsbar.pack(side='right', fill='y')
            else:
                # hide the overlay scrollbar when not needed
                try:
                    if self._vsbar.winfo_manager() == 'place':
                        self._vsbar.place_forget()
                    elif self._vsbar.winfo_ismapped():
                        self._vsbar.pack_forget()
                    # Unset scrollcommand to avoid needless updates
                    try:
                        self._canvas.configure(yscrollcommand=lambda *a: None)
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass


    # ── Tile Layout ──
    def _arrange_tiles(self):
        if self.tile_container is None:
            return
        width = self.tile_container.winfo_width()
        if width <= 1:
            width = self._canvas.winfo_width()
        if width <= 1:
            width = 600  # fallback so tiles always get laid out
        tile_w = RomTile.ICON_SIZE + 32
        cols = max(1, width // tile_w)
        row = col = 0
        for rom_path_str, tile in self.tiles.items():
            # Anchor tiles to the top of the grid cell so all row tops align
            tile.grid(row=row, column=col, padx=6, pady=6, sticky='n')
            col += 1
            if col >= cols:
                col = 0
                row += 1
        self._canvas.configure(scrollregion=self._canvas.bbox('all'))
        # Show or hide the vertical scrollbar depending on content height
        self._update_scrollbar_visibility()

    # ── Toggle handlers ──
    def _toggle_theme(self):
        new_theme = 'light' if self._theme_name == 'dark' else 'dark'
        self.config['theme'] = new_theme
        save_config(self.config)
        self.apply_theme(new_theme)
        if self._theme_label:
            try:
                self._theme_label.config(text='Theme: {}'.format(new_theme))
            except Exception:
                pass
        self._canvas_container.configure(bg=self._bg_color())
        self._canvas.configure(background=self._bg_color())
        self.tile_container.configure(background=self._bg_color())
        for tile in self.tiles.values():
            tile.refresh_theme(new_theme)
        self._arrange_tiles()
        # Titles button is a themed ttk.Button; no direct bg/fg configuration needed
        # Save show_titles preference
        self.config['show_titles'] = self.show_titles.get()

    def _update_titles_button(self):
        if self.show_titles.get():
            self.titles_btn.config(text='Hide Titles')
        else:
            self.titles_btn.config(text='Show Titles')

    def _toggle_titles(self):
        self.show_titles.set(not self.show_titles.get())
        self._update_titles_button()
        for tile in self.tiles.values():
            tile.on_toggle_titles()
        # Persist show_titles preference
        self.config['show_titles'] = self.show_titles.get()
        try:
            save_config(self.config)
        except Exception:
            pass

    def _show_config_dialog(self):
        """Open a dialog to edit config values without editing config.json directly."""
        dlg = tk.Toplevel(self.root)
        dlg.title('mGBA Launcher - Configuration')
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.protocol('WM_DELETE_WINDOW', dlg.destroy)

        # Current theme colors
        bg, fg, card, accent = _configure_base_styles(self._theme_name)
        palette = THEMES[self._theme_name]
        tb = palette['tb']
        dlg.configure(bg=bg)

        pad = {'padx': 10, 'pady': 6}
        roms_var = tk.StringVar(value=self.config.get('roms_folder', ''))
        icons_var = tk.StringVar(value=self.config.get('icons_folder', ''))
        mgba_var = tk.StringVar(value=self.config.get('mgba_exe', ''))
        theme_var = tk.StringVar(value=self.config.get('theme', 'dark'))
        show_titles_var = tk.BooleanVar(value=self.config.get('show_titles', True))

        def _browse_dir(var, title):
            d = filedialog.askdirectory(title=title, parent=dlg)
            if d:
                var.set(d)

        def _browse_exe(var, title):
            f = filedialog.askopenfilename(title=title, parent=dlg,
                filetypes=[('Executable files', '*.exe'), ('All files', '*.*')])
            if f:
                var.set(f)

        def _make_entry(parent, var):
            e = tk.Entry(parent, textvariable=var, width=42,
                         bg=card, fg=fg, insertbackground=fg,
                         relief='flat', highlightthickness=1,
                         highlightbackground=tb, highlightcolor=accent,
                         font=('Segoe UI', 9))
            return e

        def _section(title):
            outer = tk.Frame(dlg, bg=bg)
            outer.pack(fill='x', **pad)
            lbl = tk.Label(outer, text=title, bg=bg, fg=fg,
                           font=('Segoe UI', 9, 'bold'), anchor='w')
            lbl.pack(fill='x', padx=2, pady=(0, 2))
            inner = tk.Frame(outer, bg=card, highlightthickness=1,
                             highlightbackground=tb)
            inner.pack(fill='x')
            return inner

        # ROMs folder
        sec = _section('ROMs Folder')
        row = tk.Frame(sec, bg=card)
        row.pack(fill='x', padx=6, pady=6)
        _make_entry(row, roms_var).pack(side='left', fill='x', expand=True, padx=(0, 6))
        ttk.Button(row, text='Browse',
                   command=lambda: _browse_dir(roms_var, 'Select ROMs Folder')).pack(side='left')

        # Icons folder
        sec = _section('Icons Folder')
        row = tk.Frame(sec, bg=card)
        row.pack(fill='x', padx=6, pady=6)
        _make_entry(row, icons_var).pack(side='left', fill='x', expand=True, padx=(0, 6))
        ttk.Button(row, text='Browse',
                   command=lambda: _browse_dir(icons_var, 'Select Icons Folder')).pack(side='left')

        # mGBA.exe
        sec = _section('mGBA Executable')
        row = tk.Frame(sec, bg=card)
        row.pack(fill='x', padx=6, pady=6)
        _make_entry(row, mgba_var).pack(side='left', fill='x', expand=True, padx=(0, 6))
        ttk.Button(row, text='Browse',
                   command=lambda: _browse_exe(mgba_var, 'Select mGBA.exe')).pack(side='left')

        # Theme
        sec = _section('Theme')
        row = tk.Frame(sec, bg=card)
        row.pack(fill='x', padx=6, pady=6)
        ttk.Radiobutton(row, text='Dark', variable=theme_var, value='dark').pack(side='left', padx=(0, 12))
        ttk.Radiobutton(row, text='Light', variable=theme_var, value='light').pack(side='left')

        # Titles
        sec = _section('Titles')
        row = tk.Frame(sec, bg=card)
        row.pack(fill='x', padx=6, pady=6)
        ttk.Checkbutton(row, text='Show ROM titles', variable=show_titles_var).pack(side='left')

        # Buttons
        btn_row = tk.Frame(dlg, bg=bg)
        btn_row.pack(fill='x', **pad)

        def on_apply():
            self.config['roms_folder'] = roms_var.get().strip()
            self.config['icons_folder'] = icons_var.get().strip()
            self.config['mgba_exe'] = mgba_var.get().strip()
            new_theme = theme_var.get()
            new_show_titles = show_titles_var.get()

            if new_theme != self.config.get('theme', 'dark'):
                self.config['theme'] = new_theme
                self.apply_theme(new_theme)
                self._canvas_container.configure(bg=self._bg_color())
                self._canvas.configure(background=self._bg_color())
                self.tile_container.configure(bg=self._bg_color())
                for tile in self.tiles.values():
                    tile.refresh_theme(new_theme)
                self._arrange_tiles()

            self.config['show_titles'] = new_show_titles
            self.show_titles.set(new_show_titles)
            self._update_titles_button()
            for tile in self.tiles.values():
                tile.on_toggle_titles()

            save_config(self.config)
            self._populate_tiles()
            dlg.destroy()   # close the dialog on Apply

        def on_cancel():
            dlg.destroy()

        ttk.Button(btn_row, text='Cancel', command=on_cancel).pack(side='right', padx=(4, 0))
        ttk.Button(btn_row, text='Apply', command=on_apply).pack(side='right')

        dlg.bind('<Escape>', lambda e: on_cancel())
        dlg.update_idletasks()
        w = dlg.winfo_reqwidth()
        h = dlg.winfo_reqheight()
        x = self.root.winfo_rootx() + self.root.winfo_width() // 2 - w // 2
        y = self.root.winfo_rooty() + self.root.winfo_height() // 2 - h // 2
        dlg.geometry(f'+{x}+{y}')
        dlg.focus_set()

    # ── ROM Scanning ──
    def _scan_roms(self):
        roms_folder = Path(self.config.get('roms_folder', ''))
        if not roms_folder or not roms_folder.is_dir():
            messagebox.showwarning(
                'Missing ROMs Folder',
                'ROMs folder not found:\n  {}\n\n'
                'Please restart and select a valid folder.'.format(roms_folder))
            return []
        roms = [f for f in roms_folder.iterdir()
                if f.is_file() and f.suffix.lower() in ROM_EXTENSIONS]
        sort_mode = self.config.get('sort_mode', 'name')
        if sort_mode == 'date_new':
            roms.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        elif sort_mode == 'date_old':
            roms.sort(key=lambda f: f.stat().st_mtime)
        elif sort_mode == 'name_desc':
            roms.sort(key=lambda f: f.name.lower(), reverse=True)
        else:
            roms.sort(key=lambda f: f.name.lower())
        return roms

    def _find_icon(self, rom_name):
        icons_folder = Path(self.config.get('icons_folder', ''))
        if not icons_folder or not icons_folder.is_dir():
            return None

        # Direct exact match first (RomName.png / .jpg / etc.)
        for ext in ICON_EXTENSIONS:
            icon_path = icons_folder / '{}{}'.format(rom_name, ext)
            if icon_path.exists():
                return icon_path

        # Fall back to normalized + fuzzy matching
        target = normalize_name(rom_name)
        if not target:
            return None
        best = None
        best_ratio = 0.0
        for icon in icons_folder.iterdir():
            if not icon.is_file():
                continue
            candidate = normalize_name(icon.stem)
            if not candidate:
                continue
            if candidate == target:
                return icon
            ratio = SequenceMatcher(None, target, candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best = icon
        if best is not None and best_ratio >= 0.75:
            return best
        return None

    def _populate_tiles(self):
        for tile in self.tiles.values():
            tile.destroy()
        self.tiles.clear()
        roms = self._scan_roms()
        # Ensure RomTile uses the current icon size when building
        RomTile.ICON_SIZE = self.icon_size
        for rom_path in roms:
            rom_name = rom_path.stem
            icon_path = self._find_icon(rom_name)
            tile = RomTile(
                self.tile_container,
                rom_name=rom_name,
                rom_path=rom_path,
                icon_path=icon_path,
                show_titles=self.show_titles,
                launch_callback=self._launch_rom,
                theme_name=self._theme_name)
            self.tiles[str(rom_path)] = tile
        self._arrange_tiles()
        # Re-arrange once the window is mapped/sized (the canvas Configure
        # handler also keeps the container width in sync)
        self.root.after(50, self._arrange_tiles)

    # ── Launch ──
    def _launch_rom(self, rom_path):
        mgba_exe = self.config.get('mgba_exe', '')
        if not mgba_exe or not Path(mgba_exe).exists():
            messagebox.showerror(
                'mGBA Not Found',
                'mGBA executable not found:\n  {}\n\n'
                'Please restart and select mGBA.exe in setup.'.format(mgba_exe))
            return
        subprocess.Popen(
            [mgba_exe, str(rom_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)


# ── Entry Point ──

def main():
    app = App()
    app.run()


if __name__ == '__main__':
    main()
