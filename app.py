"""Windows entry point. Based on the user's DeepSeekAssistant interaction flow."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import pyautogui
import pyperclip
from core import (VERSION, DATA, MODELS, IS_MAC, OS_NAME, FlowError, hardware, recommend, load_config,
                  save_config, event, provision, infer)
from prompts import build_prompt
from catalog import PROVIDERS, CUSTOM_PROVIDER, MODEL_LABELS, LABEL_TO_MODEL, provider_for_url, normalize_base_url
from platform_bridge import (capture_selection, replace_selection, same_text,
                                 foreground_is_ours, set_startup, startup_enabled)
from tasks import run_task
from appearance import THEMES, DEFAULT_THEME, valid_opacity, apply_appearance
UI_FONT = 'Helvetica Neue' if IS_MAC else 'Segoe UI'



class App:
    def __init__(self, root, background=False, test_mode=False):
        self.root = root
        self.config = load_config()
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.hotkey_tid = None
        self.hotkey_listener = None
        self.capture_lock = threading.Lock()
        self.appearance_after = None
        self.source_target = None
        self.result_ready = False
        self.result_mode = None
        self.result_input = ''
        self.result_target = None
        self.popup_mode = False
        self.ignore_hide_until = 0
        self.tray = None
        self.tray_ready = False
        self.hotkey_ready = False
        self.hotkey_name = '⌃⌥G' if IS_MAC else 'Ctrl+Alt+G'
        self.background = background
        self.test_mode = test_mode
        root.title('ResearchFlow AI · ' + OS_NAME + ' Beta ' + VERSION)
        root.geometry(f"{min(900, root.winfo_screenwidth()-60)}x{min(800, root.winfo_screenheight()-80)}")
        root.minsize(740, 650)
        root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style()
        self.style = style
        style.theme_use('clam')
        style.configure('TButton', padding=7)
        outer = ttk.Frame(root, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='ResearchFlow AI', font=(UI_FONT, 22, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='科研阅读与写作助手 · 本地优先 · '+OS_NAME+' Beta').pack(anchor='w', pady=(0, 10))
        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=(0, 5))
        ttk.Button(controls, text='隐藏到托盘', command=self.hide).pack(side='right')
        self.hotkey_hint = tk.StringVar(value=self.hotkey_name + ' 唤起划词助手；托盘菜单可重新打开')
        ttk.Label(controls, textvariable=self.hotkey_hint).pack(side='left')
        self.book = ttk.Notebook(outer)
        self.work = ttk.Frame(self.book, padding=12)
        setup_page = ttk.Frame(self.book)
        setup_canvas = tk.Canvas(setup_page, highlightthickness=0)
        setup_scroll = ttk.Scrollbar(setup_page, orient='vertical', command=setup_canvas.yview)
        setup_canvas.configure(yscrollcommand=setup_scroll.set)
        setup_scroll.pack(side='right', fill='y')
        setup_canvas.pack(side='left', fill='both', expand=True)
        self.setup = ttk.Frame(setup_canvas, padding=12)
        setup_window = setup_canvas.create_window((0, 0), window=self.setup, anchor='nw')
        self.setup.bind('<Configure>', lambda e: setup_canvas.configure(scrollregion=setup_canvas.bbox('all')))
        def resize_setup(event):
            setup_canvas.itemconfigure(setup_window, width=event.width)
            for child in self.setup.winfo_children():
                if isinstance(child, ttk.Label):
                    child.configure(wraplength=max(250, event.width-35))
        setup_canvas.bind('<Configure>', resize_setup)
        self.setup_page = setup_page
        self.book.add(self.work, text='翻译 / 润色 / 纠错 / 解释')
        self.book.add(setup_page, text='首次配置与诊断')
        self.preferences_page = ttk.Frame(self.book)
        pref_canvas = tk.Canvas(self.preferences_page, highlightthickness=0)
        pref_scroll = ttk.Scrollbar(self.preferences_page, orient='vertical', command=pref_canvas.yview)
        pref_canvas.configure(yscrollcommand=pref_scroll.set)
        pref_scroll.pack(side='right', fill='y'); pref_canvas.pack(side='left', fill='both', expand=True)
        self.preferences = ttk.Frame(pref_canvas, padding=16)
        pref_window = pref_canvas.create_window((0, 0), window=self.preferences, anchor='nw')
        self.preferences.bind('<Configure>', lambda e: pref_canvas.configure(scrollregion=pref_canvas.bbox('all')))
        pref_canvas.bind('<Configure>', lambda e: pref_canvas.itemconfigure(pref_window, width=e.width))
        self.book.add(self.preferences_page, text='使用偏好')
        def wheel(event):
            active = self.book.select()
            canvas = setup_canvas if active == str(setup_page) else pref_canvas if active == str(self.preferences_page) else None
            if canvas and event.delta:
                canvas.yview_scroll((-1 if event.delta > 0 else 1) * max(1, int(abs(event.delta)/120)), 'units')
        root.bind('<MouseWheel>', wheel)
        ttk.Label(self.work, text='在其他应用选中文字，按上方显示的快捷键；也可以粘贴到下方。').pack(anchor='w')
        self.hotkey_status = ttk.Label(self.work, text='正在注册全局快捷键…')
        self.hotkey_status.pack(anchor='w', pady=(2, 8))
        input_label = ttk.Label(self.work, text='原文（最多 12,000 字符）')
        input_label.pack(anchor='w')
        self.input = tk.Text(self.work, height=4, wrap='word', font=(UI_FONT, 11), undo=True)
        self.input.pack(fill='both', expand=True, pady=5)
        row = ttk.Frame(self.work)
        action_row = row
        row.pack(fill='x')
        self.actions = []
        for label, mode in [('翻译（中英自动）', 'translate'), ('润色', 'polish'), ('纠错', 'check'), ('解释', 'explain')]:
            b = ttk.Button(row, text=label, command=lambda m=mode: self.process(m))
            b.pack(side='left', padx=(0, 8))
            self.actions.append(b)
        output_label = ttk.Label(self.work, text='结果')
        output_label.pack(anchor='w', pady=(10, 0))
        self.output = tk.Text(self.work, height=10, wrap='word', font=(UI_FONT, 11), state='disabled')
        self.output.pack(fill='both', expand=True, pady=5)
        row = ttk.Frame(self.work)
        result_row = row
        row.pack(side='bottom', fill='x', before=self.input)
        self.copy_button = ttk.Button(row, text='一键复制', command=self.copy, state='disabled')
        self.copy_button.pack(side='left')
        self.replace_button = ttk.Button(row, text='一键替换原选区', command=self.replace, state='disabled')
        self.replace_button.pack(side='left', padx=8)
        ttk.Button(row, text='清空', command=self.clear).pack(side='right')
        replacement_hint = ttk.Label(self.work, text='替换须原应用可编辑，且原选区保持不变。', wraplength=680)
        replacement_hint.pack(side='bottom', before=self.input, anchor='w', pady=(5, 0))
        # Reserve the result actions and divide remaining space between both
        # text boxes, so minimum-size windows never lose their copy buttons.
        for child in self.work.pack_slaves():
            child.pack_forget()
        self.work.columnconfigure(0, weight=1)
        self.work.rowconfigure(1, weight=1, minsize=42)
        self.work.rowconfigure(4, weight=3, minsize=70)
        for index, child in enumerate((input_label, self.input, action_row, output_label,
                                        self.output, result_row, replacement_hint)):
            child.grid(row=index, column=0, sticky='nsew' if index in (1, 4) else 'ew',
                       pady=(2, 2))
        self.hw_text = tk.StringVar(value='正在检测 Windows、内存、显卡和磁盘…')
        ttk.Label(self.setup, textvariable=self.hw_text, wraplength=760, justify='left').pack(anchor='w', pady=(0, 12))
        self.mode = tk.StringVar(value=self.config['mode'])
        row = ttk.Frame(self.setup)
        row.pack(fill='x')
        ttk.Radiobutton(row, text='本地模式（无需密钥）', variable=self.mode, value='local').pack(side='left')
        ttk.Radiobutton(row, text='云端模式（需自行提供 API）', variable=self.mode, value='cloud').pack(side='left', padx=15)
        ttk.Label(self.setup, text='本地模型').pack(anchor='w', pady=(12, 3))
        self.model = tk.StringVar(value=MODEL_LABELS.get(self.config['model'], MODEL_LABELS['deepseek-r1:1.5b']))
        ttk.Combobox(self.setup, textvariable=self.model, values=list(MODEL_LABELS.values()), state='readonly', width=70).pack(fill='x')
        ttk.Label(self.setup, text='大小为模型权重的近似磁盘占用，实际以下载进度为准；另需引擎与运行空间。', wraplength=760).pack(anchor='w', pady=3)
        ttk.Label(self.setup, text='配置会联网下载 Ollama 和模型，并运行真实推理检查。已安装的引擎和模型会优先复用。',
                  wraplength=760).pack(anchor='w', pady=6)
        self.cloud_url = tk.StringVar(value=self.config['cloud_url'])
        self.cloud_model = tk.StringVar(value=self.config['cloud_model'])
        self.key = tk.StringVar()
        self.provider = tk.StringVar(value=provider_for_url(self.config['cloud_url']))
        ttk.Label(self.setup, text='API 供应商').pack(anchor='w', pady=(10, 2))
        provider_box = ttk.Combobox(self.setup, textvariable=self.provider, values=list(PROVIDERS), state='readonly')
        provider_box.pack(fill='x')
        provider_box.bind('<<ComboboxSelected>>', self.provider_changed)
        for label, var, mask in [('云端 HTTPS API 基础地址', self.cloud_url, ''),
                                  ('模型名（用户可自定义；填写供应商支持的模型 ID）', self.cloud_model, ''), ('API Key（所选供应商创建的密钥，只保存在本次运行内存）', self.key, '•')]:
            ttk.Label(self.setup, text=label).pack(anchor='w', pady=(6, 2))
            if var is self.cloud_model:
                self.cloud_model_box = ttk.Combobox(self.setup, textvariable=var,
                    values=PROVIDERS[self.provider.get()][1])
                self.cloud_model_box.pack(fill='x')
            else:
                ttk.Entry(self.setup, textvariable=var, show=mask).pack(fill='x')
        ttk.Label(self.setup, text='选择供应商会填入示例地址和模型名；两者均可修改。密钥不会自动识别供应商。', wraplength=760).pack(anchor='w', pady=5)
        self.cloud_consent = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.setup, text='我同意云端模式将所选文本发送给以上服务商，并可能产生 API 费用。',
                        variable=self.cloud_consent).pack(anchor='w', pady=10)
        self.cloud_url.trace_add('write', self.endpoint_changed)
        self.autostart = tk.BooleanVar(value=False if test_mode else startup_enabled())
        self.auto_hide = tk.BooleanVar(value=self.config.get('auto_hide', False))
        ttk.Label(self.preferences, text='启动与弹窗', font=(UI_FONT, 16, 'bold')).pack(anchor='w', pady=(0, 15))
        ttk.Checkbutton(self.preferences, text='登录 ' + OS_NAME + ' 后自动启动（后台运行）', variable=self.autostart,
                        command=self.save_preferences).pack(anchor='w', pady=3)
        ttk.Checkbutton(self.preferences, text='划词弹窗点击其他应用时自动隐藏', variable=self.auto_hide,
                        command=self.save_preferences).pack(anchor='w', pady=3)
        ttk.Label(self.preferences, text='这两项勾选后立即保存。隐藏后可按窗口顶部显示的快捷键、双击程序入口，\n或使用系统托盘菜单重新打开。关闭窗口或托盘菜单“退出”会结束程序。',
                  wraplength=680, justify='left').pack(anchor='w', pady=12)
        ttk.Separator(self.preferences).pack(fill='x', pady=10)
        ttk.Label(self.preferences, text='面板外观', font=(UI_FONT, 16, 'bold')).pack(anchor='w', pady=(0, 8))
        self.theme = tk.StringVar(value=self.config.get('theme', DEFAULT_THEME))
        theme_box = ttk.Combobox(self.preferences, textvariable=self.theme, values=list(THEMES), state='readonly')
        theme_box.pack(fill='x', pady=4)
        theme_box.bind('<<ComboboxSelected>>', lambda e: self.preview_appearance())
        self.opacity = tk.DoubleVar(value=valid_opacity(self.config.get('opacity', 1.0)) * 100)
        self.opacity_label = tk.StringVar(value=f'不透明度：{self.opacity.get():.0f}%')
        ttk.Label(self.preferences, textvariable=self.opacity_label).pack(anchor='w', pady=(10, 2))
        ttk.Scale(self.preferences, from_=70, to=100, variable=self.opacity, command=lambda v: self.preview_appearance()).pack(fill='x')
        ttk.Label(self.preferences, text='70%–100%，拖动即时预览，停止调整后自动保存。').pack(anchor='w', pady=4)
        ttk.Button(self.preferences, text='恢复默认外观', command=self.reset_appearance).pack(anchor='w', pady=6)
        if IS_MAC:
            ttk.Label(self.preferences, text='Mac 划词与替换需要“辅助功能”，全局快捷键还需“输入监控”。\n请在系统设置中手动授权本应用，然后重新启动。', wraplength=660).pack(anchor='w', pady=8)
            ttk.Button(self.preferences, text='打开 macOS 权限设置', command=self.open_mac_permissions).pack(anchor='w')
        row = ttk.Frame(self.setup)
        row.pack(fill='x', pady=5)
        self.setup_button = ttk.Button(row, text='保存并配置 / 重试', command=self.configure)
        self.setup_button.pack(side='left')
        ttk.Button(row, text='重新检测硬件', command=self.detect).pack(side='left', padx=8)
        ttk.Button(row, text='打开诊断日志', command=self.open_logs).pack(side='left')
        ttk.Label(self.setup, text='日志只记录事件代码与时间，不记录原文、结果、密钥或服务器响应。\n'
            '关闭窗口会退出；隐藏后仍在托盘运行。卸载本助手不会删除共享 Ollama 或模型。',
            wraplength=760, justify='left').pack(anchor='w', pady=12)
        self.status = tk.StringVar(value='就绪。请选择原文后使用上方快捷键，或粘贴到输入框。' if self.config.get('configured') else '请先在“首次配置与诊断”中完成配置。')
        footer = ttk.Frame(outer)
        footer.pack(side='bottom', fill='x')
        status_label = ttk.Label(footer, textvariable=self.status, wraplength=810)
        status_label.pack(fill='x', pady=(10, 5))
        footer.bind('<Configure>', lambda e: status_label.configure(wraplength=max(250, e.width-10)))
        self.bar = ttk.Progressbar(footer, maximum=100)
        self.bar.pack(fill='x')
        ttk.Button(footer, text='取消当前操作', command=self.cancel_operation).pack(anchor='e', pady=(6, 0))
        self.book.pack(fill='both', expand=True)
        root.after(80, self.drain)
        self.book.select(self.work if self.config.get('configured') else self.setup_page)
        if not test_mode:
            self.detect()
            threading.Thread(target=self.hotkeys, daemon=True).start()
            if IS_MAC:
                self.run_tray()  # Cocoa menu bar objects must be created on the main thread.
            else:
                threading.Thread(target=self.run_tray, daemon=True).start()
            root.after(1200, self.initial_visibility)
            root.after(250, self.watch_focus)
        if not test_mode:
            event('START')
        apply_appearance(root, self.style, self.theme.get(), self.opacity.get()/100)

    def detect(self):
        def task():
            try:
                self.q.put(('hardware', hardware()))
            except Exception:
                self.q.put(('status', '硬件检测失败；可重试或使用云端模式。'))
        threading.Thread(target=task, daemon=True).start()

    def snapshot(self):
        return {'mode': self.mode.get(), 'model': LABEL_TO_MODEL.get(self.model.get(), ''),
                'cloud_url': normalize_base_url(self.cloud_url.get()), 'cloud_model': self.cloud_model.get().strip(),
                'provider': self.provider.get(), 'autostart': self.autostart.get(), 'auto_hide': self.auto_hide.get(),
                'configured': self.config.get('configured', False),
                'theme': self.theme.get(), 'opacity': valid_opacity(self.opacity.get()/100)}

    def preview_appearance(self):
        apply_appearance(self.root, self.style, self.theme.get(), self.opacity.get()/100)
        self.opacity_label.set(f'不透明度：{self.opacity.get():.0f}%')
        if self.appearance_after:
            self.root.after_cancel(self.appearance_after)
        self.appearance_after = self.root.after(500, self.save_appearance)

    def save_appearance(self):
        self.appearance_after = None
        if self.test_mode:
            return
        try:
            cfg = load_config()
            cfg.update(theme=self.theme.get(), opacity=valid_opacity(self.opacity.get()/100))
            save_config(cfg)
            event('APPEARANCE')
        except OSError:
            self.status.set('外观已预览，但保存失败。请检查磁盘空间。')

    def reset_appearance(self):
        self.theme.set(DEFAULT_THEME); self.opacity.set(100)
        self.preview_appearance()

    def open_logs(self):
        DATA.mkdir(parents=True, exist_ok=True)
        if IS_MAC:
            import subprocess
            subprocess.Popen(['/usr/bin/open', str(DATA)])
        else:
            os.startfile(DATA)

    def open_mac_permissions(self):
        from macos_integration import open_permission_settings
        open_permission_settings()

    def endpoint_changed(self, *args):
        self.cloud_consent.set(False)
        self.key.set('')

    def provider_changed(self, event=None):
        base, models = PROVIDERS[self.provider.get()]
        self.cloud_url.set(base)
        self.cloud_model.set(models[0] if models else '')
        self.cloud_model_box.configure(values=models)
        self.key.set('')
        self.cloud_consent.set(False)

    def save_preferences(self):
        try:
            if not self.test_mode:
                set_startup(self.autostart.get())
            cfg = load_config()
            if not cfg.get('configured'):
                cfg['model'] = LABEL_TO_MODEL.get(self.model.get(), cfg['model'])
            cfg.update(autostart=self.autostart.get(), auto_hide=self.auto_hide.get())
            save_config(cfg)
            self.status.set('启动与隐藏偏好已保存。')
        except OSError:
            self.autostart.set(startup_enabled())
            self.status.set('无法保存开机启动设置，请检查当前账户权限。')

    def run_tray(self):
        try:
            if IS_MAC:
                from macos_integration import MacTray
                self.tray = MacTray(self.q)
                self.tray_ready = True
                event('TRAY_READY')
                return
            import pystray
            from PIL import Image, ImageDraw
            icon = Image.new('RGB', (64, 64), '#173d53')
            draw = ImageDraw.Draw(icon)
            draw.text((12, 19), 'RF', fill='white', font_size=26)
            self.tray = pystray.Icon('ResearchFlowAI', icon, 'ResearchFlow AI', menu=pystray.Menu(
                pystray.MenuItem('打开 ResearchFlow AI', lambda *a: self.q.put(('show', None)), default=True),
                pystray.MenuItem('隐藏', lambda *a: self.q.put(('hide', None))),
                pystray.MenuItem('退出', lambda *a: self.q.put(('exit', None)))))
            self.tray.run(setup=lambda icon: self.tray_started(icon))
        except Exception:
            event('TRAY')
            self.q.put(('status', '托盘不可用；可使用 Ctrl+Alt+G 重新打开。'))

    def tray_started(self, icon):
        icon.visible = True
        self.tray_ready = True
        event('TRAY_READY')

    def initial_visibility(self):
        if self.background and self.config.get('configured'):
            self.hide()

    def show(self, popup=False):
        self.popup_mode = popup
        self.ignore_hide_until = time.monotonic() + .7
        self.root.deiconify()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(250, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()
        if IS_MAC:
            from macos_integration import bring_to_front
            bring_to_front()

    def hide(self):
        if not (self.tray_ready or self.hotkey_ready or self.test_mode):
            self.status.set('托盘和快捷键尚未就绪，暂不隐藏以免无法重新打开。')
            return
        self.popup_mode = False
        self.root.withdraw()

    def watch_focus(self):
        if (self.popup_mode and self.auto_hide.get() and self.root.state() == 'normal'
                and time.monotonic() > self.ignore_hide_until and not foreground_is_ours()):
            self.hide()
        self.root.after(250, self.watch_focus)

    def refresh_result_buttons(self):
        self.copy_button.state(['!disabled'] if self.result_ready and not self.busy else ['disabled'])
        self.replace_button.state(['!disabled'] if self.result_ready and not self.busy and self.result_target
                                  and self.result_mode in ('translate', 'polish', 'check') else ['disabled'])

    def start(self, fn):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.setup_button.state(['disabled'])
        for b in self.actions:
            b.state(['disabled'])
        self.refresh_result_buttons()
        def worker():
            try:
                fn()
            except FlowError as e:
                event(e.code)
                self.q.put(('status', str(e)))
            except Exception:
                event('INTERNAL')
                self.q.put(('status', '操作失败（INTERNAL）。请重试并查看诊断日志。'))
            finally:
                self.q.put(('finished', None))
        threading.Thread(target=worker, daemon=True).start()

    def progress(self, text, percent=0):
        self.q.put(('progress', (text, percent)))

    def consent(self, config):
        if config['mode'] == 'cloud' and not self.cloud_consent.get():
            messagebox.showinfo('云端授权', '请先在配置页勾选云端文本发送确认。')
            self.book.select(self.setup_page)
            return False
        return True

    def configure(self):
        cfg, key = self.snapshot(), self.key.get()
        if not self.consent(cfg):
            return
        def run():
            if cfg['mode'] == 'local':
                provision(cfg['model'], self.progress, self.cancel)
            else:
                self.progress('执行云端真实推理检查…')
                infer(cfg, 'Reply with the word READY.', key, self.cancel)
                self.progress('云端真实推理检查通过。', 100)
            cfg['configured'] = True
            save_config(cfg)
            self.q.put(('configured', cfg))
        self.status.set('正在配置…')
        self.start(run)

    def process(self, mode):
        if self.busy:
            return
        raw_text = self.input.get('1.0', 'end-1c')
        text = raw_text.strip()
        if not text:
            self.status.set('请先划词或粘贴原文。')
            return
        if len(text) > 12000:
            self.status.set('原文超过 12,000 字符，请分段处理。')
            return
        cfg, key = self.snapshot(), self.key.get()
        if not self.consent(cfg):
            return
        self.set_output('')
        self.result_ready = False
        self.result_target = None
        target = dict(self.source_target) if self.source_target and same_text(raw_text, self.source_target['original']) else None
        self.status.set('正在生成；首次加载模型可能较慢…')
        def run():
            last = [0]
            def stream(value):
                if time.monotonic() - last[0] > .15:
                    self.q.put(('output', value))
                    last[0] = time.monotonic()
            answer = run_task(cfg, mode, text, key, self.cancel, stream, self.progress)
            self.q.put(('complete', (answer, mode, raw_text, target)))
            self.q.put(('status', '已完成。请核对结果，尤其是科研事实、数字与术语。'))
        self.start(run)

    def set_output(self, text):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', text)
        self.output.configure(state='disabled')

    def copy(self):
        if not self.result_ready or self.busy:
            return
        value = self.output.get('1.0', 'end-1c')
        if value:
            try:
                pyperclip.copy(value)
                self.status.set('结果已复制。')
            except Exception:
                self.status.set('剪贴板正忙，请重试。')

    def replace(self):
        if self.busy or not self.result_ready or self.result_mode not in ('translate', 'polish', 'check'):
            return
        target = self.result_target
        current = self.input.get('1.0', 'end-1c')
        if not target or not same_text(current, self.result_input) or not same_text(current, target['original']):
            self.status.set('原文已修改或没有原选区，未替换。请重新划词或使用一键复制。')
            return
        answer = self.output.get('1.0', 'end-1c')
        self.status.set('正在核对原窗口和原选区…')
        self.ignore_hide_until = time.monotonic() + 5
        self.root.withdraw()
        self.popup_mode = False
        def run():
            try:
                replace_selection(target, answer)
                event('REPLACE')
                self.q.put(('status', '已向原应用发送替换；请核对结果，可在原应用 Ctrl+Z 撤销。'))
            finally:
                self.q.put(('replaced', None))
                self.q.put(('show', None))
        self.start(run)

    def clear(self):
        if not self.busy:
            self.input.delete('1.0', 'end')
            self.set_output('')
            self.source_target = None
            self.result_target = None
            self.result_ready = False
            self.refresh_result_buttons()

    def cancel_operation(self):
        if self.busy:
            self.cancel.set()
            self.status.set('已请求取消；等待当前网络读取返回。Ollama 安装期间需等待官方安装器结束。')

    def hotkeys(self):
        if IS_MAC:
            return self.macos_hotkeys()
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        self.hotkey_tid = k.GetCurrentThreadId()
        # Signature setup is essential for 64-bit handles and pointers.
        u.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        active = None
        for name, modifiers, key in [('Ctrl+Alt+G', 0x4003, 0x47), ('Ctrl+Alt+R', 0x4003, 0x52),
                                      ('Ctrl+Shift+Space', 0x4006, 0x20)]:
            if u.RegisterHotKey(None, 1, modifiers, key):
                active = name
                break
        if active is None:
            event('HOTKEY_CONFLICT')
            self.q.put(('hotkey', '三个备用快捷键均被占用；可从托盘打开后手动粘贴。'))
            return
        self.hotkey_ready = True
        event('HOTKEY_READY')
        if active != 'Ctrl+Alt+G':
            event('HOTKEY_CONFLICT')
        self.q.put(('hotkey_active', active))
        msg = wintypes.MSG()
        try:
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    if self.busy:
                        self.q.put(('show', None))
                        continue
                    try:
                        value = capture_selection()
                        self.q.put(('selection', value))
                    except Exception:
                        self.q.put(('status', '划词获取失败。可使用 Ctrl+C 后手动粘贴。'))
        finally:
            u.UnregisterHotKey(None, 1)

    def macos_hotkeys(self):
        try:
            from macos_integration import permission_status
            if not permission_status():
                raise FlowError('PERMISSION', '请在“使用偏好”打开 Mac 权限说明，授权辅助功能和输入监控后重启。')
            from pynput.keyboard import GlobalHotKeys
            def trigger():
                self.q.put(('capture_hotkey', None))
            self.hotkey_listener = GlobalHotKeys({'<ctrl>+<alt>+g': trigger})
            self.hotkey_listener.start()
            if not self.hotkey_listener.IS_TRUSTED:
                self.hotkey_listener.stop()
                raise FlowError('PERMISSION', 'Mac 尚未允许监听快捷键，请授权辅助功能和输入监控后重启。')
            self.hotkey_ready = True
            self.q.put(('hotkey_active', '⌃⌥G'))
            self.hotkey_listener.join()
        except Exception:
            event('PERMISSION')
            self.q.put(('hotkey', 'Mac 快捷键未就绪，请在“使用偏好”查看权限说明；仍可手动粘贴。'))

    def capture_mac_request(self):
        if self.busy:
            self.show(); return
        def worker():
            if not self.capture_lock.acquire(False):
                return
            try:
                self.q.put(('selection', capture_selection()))
            except FlowError as exc:
                self.q.put(('status', str(exc)))
                self.q.put(('show', None))
            except Exception:
                self.q.put(('status', 'Mac 划词失败，请检查权限或手动粘贴。'))
            finally:
                self.capture_lock.release()
        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        try:
            while True:
                kind, value = self.q.get_nowait()
                if kind == 'status':
                    self.status.set(value)
                elif kind == 'progress':
                    self.status.set(value[0])
                    self.bar['value'] = value[1]
                elif kind == 'output':
                    self.set_output(value)
                elif kind == 'complete':
                    answer, mode, original, target = value
                    self.set_output(answer)
                    self.result_ready = True
                    self.result_mode = mode
                    self.result_input = original
                    self.result_target = target
                    self.refresh_result_buttons()
                elif kind == 'replaced':
                    self.source_target = None
                    self.result_target = None
                elif kind == 'show':
                    self.show()
                elif kind == 'hide':
                    self.hide()
                elif kind == 'exit':
                    self.close()
                    return
                elif kind == 'finished':
                    self.busy = False
                    self.setup_button.state(['!disabled'])
                    for b in self.actions:
                        b.state(['!disabled'])
                    self.refresh_result_buttons()
                elif kind == 'configured':
                    value.update(theme=self.theme.get(), opacity=valid_opacity(self.opacity.get()/100))
                    self.config = value
                    if not self.test_mode:
                        save_config(value)
                    self.book.select(self.work)
                elif kind == 'capture_hotkey':
                    self.capture_mac_request()
                elif kind == 'hotkey':
                    self.hotkey_status.configure(text=value)
                    self.hotkey_hint.set('快捷键不可用；请从系统托盘打开后手动粘贴')
                    self.status.set(value)
                elif kind == 'hotkey_active':
                    self.hotkey_name = value
                    self.hotkey_hint.set(value + ' 唤起划词助手；托盘菜单可重新打开')
                    self.hotkey_status.configure(text='全局快捷键已就绪：' + value
                        + ('（默认组合被占用，已自动切换）' if not IS_MAC and value != 'Ctrl+Alt+G' else ''))
                elif kind == 'hardware':
                    os_label = f"macOS {value.get('macos_version', '')}" if IS_MAC else f"Windows build {value['windows_build']}"
                    self.hw_text.set(f"{os_label} / {value['arch']}\n"
                        f"内存 {value['ram_gb']} GiB（当前可用 {value['available_gb']}） · 系统盘空闲 {value['system_free_gb']} GiB\n"
                        f"模型盘空闲 {value['model_free_gb']} GiB · GPU: {value['gpu']}\n"
                        f"模型目录：{value['model_dir']}\n推荐：{recommend(value)}（保守估计，实际速度需实测）")
                    if not self.config.get('configured'):
                        self.model.set(MODEL_LABELS[recommend(value)])
                elif kind == 'selection':
                    text, target = value
                    self.show(popup=True)
                    self.book.select(self.work)
                    self.source_target = target if len(text) <= 12000 else None
                    self.result_target = None
                    self.result_ready = False
                    self.set_output('')
                    self.input.delete('1.0', 'end')
                    self.refresh_result_buttons()
                    if text:
                        self.input.insert('1.0', text[:12000])
                        self.status.set('已获取选中文字。请选择翻译、润色、纠错或解释。' if len(text) <= 12000
                                        else '选中文字过长，仅载入前 12,000 字符，已禁用替换。')
                    else:
                        self.status.set('未读取到选中文字；请手动复制粘贴。')
        except queue.Empty:
            pass
        self.root.after(80, self.drain)

    def close(self):
        if self.busy:
            messagebox.showinfo('操作进行中', '请先取消并等待当前操作结束，再关闭程序。')
            return
        self.cancel.set()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        if self.hotkey_tid and not IS_MAC:
            ctypes.windll.user32.PostThreadMessageW(self.hotkey_tid, 0x0012, 0, 0)
        self.key.set('')
        if self.appearance_after:
            self.root.after_cancel(self.appearance_after)
            self.save_appearance()
        if self.tray:
            self.tray.stop()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', metavar='REPORT')
    parser.add_argument('--background', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        # Exercise bundled imports, Tcl/Tk and hardware; no model download or key.
        r = tk.Tk()
        r.withdraw()
        result = {'version': VERSION, 'frozen': bool(getattr(sys, 'frozen', False)),
                  'tk': r.tk.call('info', 'patchlevel'), 'hardware': hardware(),
                  'prompt_modes': all(build_prompt(m, 'Test') for m in ('translate', 'explain', 'polish', 'check')),
                  'local_model_count': len(MODELS), 'provider_choices': list(PROVIDERS)}
        if IS_MAC:
            from macos_integration import MacTray
            result['tray_import'] = bool(MacTray)
        else:
            import pystray
            from PIL import Image
            result['tray_import'] = bool(pystray.Icon and Image.new('RGB', (16, 16)))
        r.destroy()
        Path(args.self_test).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return
    if IS_MAC:
        from macos_integration import run_single_instance
        run_single_instance(lambda background: App(tk.Tk(), background=background), args.background)
        return
    k = ctypes.windll.kernel32
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    mutex = k.CreateMutexW(None, False, 'Local\\ResearchFlowAI_Beta')
    already_running = k.GetLastError() == 183
    k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateEventW.restype = wintypes.HANDLE
    k.SetEvent.argtypes = [wintypes.HANDLE]
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    show_event = k.CreateEventW(None, False, False, 'Local\\ResearchFlowAI_Show')
    if already_running:
        if show_event:
            k.SetEvent(show_event)
            k.CloseHandle(show_event)
        if mutex:
            k.CloseHandle(mutex)
        return
    try:
        app = App(tk.Tk(), background=args.background)
        def poll_show():
            if show_event and k.WaitForSingleObject(show_event, 0) == 0:
                app.show()
            app.root.after(250, poll_show)
        app.root.after(250, poll_show)
        app.root.mainloop()
    finally:
        if show_event:
            k.CloseHandle(show_event)
        if mutex:
            k.CloseHandle(mutex)


if __name__ == '__main__':
    main()
