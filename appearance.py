"""Cross-platform Tk appearance with bounded opacity and readable palettes."""
THEMES = {
    '浅色 · 海蓝': {'bg': '#edf3f8', 'surface': '#ffffff', 'fg': '#172b3b', 'accent': '#22679b', 'select': '#d2e6f7'},
    '深色 · 石墨': {'bg': '#20252b', 'surface': '#2a3139', 'fg': '#edf2f7', 'accent': '#7ab6ed', 'select': '#3d5875'},
    '暖色 · 米白': {'bg': '#f4efe5', 'surface': '#fffcf5', 'fg': '#40382e', 'accent': '#8c603c', 'select': '#e9d7be'},
    '清新 · 青绿': {'bg': '#eaf3ef', 'surface': '#ffffff', 'fg': '#193c33', 'accent': '#247a65', 'select': '#c9e8dc'},
}
DEFAULT_THEME = next(iter(THEMES))


def valid_opacity(value):
    try:
        return max(.70, min(1.0, float(value)))
    except (ValueError, TypeError):
        return 1.0


def apply_appearance(root, style, theme, opacity):
    import tkinter as tk
    from tkinter import ttk
    p = THEMES.get(theme, THEMES[DEFAULT_THEME])
    style.configure('.', background=p['bg'], foreground=p['fg'], fieldbackground=p['surface'])
    for name in ('TFrame', 'TLabel', 'TCheckbutton', 'TRadiobutton', 'TLabelframe', 'TLabelframe.Label'):
        style.configure(name, background=p['bg'], foreground=p['fg'])
    style.configure('TButton', background=p['surface'], foreground=p['fg'], padding=7)
    style.map('TButton', background=[('active', p['select'])], foreground=[('disabled', '#888888')])
    style.configure('TNotebook', background=p['bg'])
    style.configure('TNotebook.Tab', background=p['bg'], foreground=p['fg'])
    style.map('TNotebook.Tab', background=[('selected', p['surface'])])
    style.configure('TEntry', fieldbackground=p['surface'], foreground=p['fg'])
    style.configure('TCombobox', fieldbackground=p['surface'], foreground=p['fg'], selectbackground=p['select'], selectforeground=p['fg'])
    style.map('TCombobox', fieldbackground=[('readonly', p['surface'])], foreground=[('readonly', p['fg'])])
    style.configure('Horizontal.TProgressbar', background=p['accent'], troughcolor=p['surface'])
    style.map('TCheckbutton', background=[('active', p['bg'])])
    style.map('TRadiobutton', background=[('active', p['bg'])])
    root.configure(background=p['bg'])
    root.option_add('*TCombobox*Listbox.background', p['surface'])
    root.option_add('*TCombobox*Listbox.foreground', p['fg'])
    def visit(widget):
        if isinstance(widget, tk.Text):
            widget.configure(background=p['surface'], foreground=p['fg'], insertbackground=p['fg'],
                             selectbackground=p['select'], selectforeground=p['fg'])
        elif isinstance(widget, tk.Canvas):
            widget.configure(background=p['bg'])
        for child in widget.winfo_children():
            visit(child)
    visit(root)
    root.attributes('-alpha', valid_opacity(opacity))
