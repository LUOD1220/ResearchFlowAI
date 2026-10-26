"""Windows selection and opt-in per-user startup. No user text is logged."""
import ctypes
from ctypes import wintypes
import os
import sys
from pathlib import Path
import time
import winreg
import pyautogui
import pyperclip
from core import FlowError

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'ResearchFlowAI'
u = ctypes.windll.user32
u.GetForegroundWindow.restype = wintypes.HWND
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.IsWindow.argtypes = [wintypes.HWND]
u.SetForegroundWindow.argtypes = [wintypes.HWND]
u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
u.IsIconic.argtypes = [wintypes.HWND]


def owner_pid(hwnd):
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def foreground_is_ours():
    return owner_pid(u.GetForegroundWindow()) == os.getpid()


def capture_text():
    for _ in range(100):
        if not any(u.GetAsyncKeyState(k) & 0x8000 for k in (0x11, 0x12, 0x10, 0x47, 0x52, 0x20)):
            break
        time.sleep(.02)
    else:
        return ''
    old = pyperclip.paste()
    last_seq = None
    try:
        for keys in (('ctrl', 'c'), ('ctrl', 'insert')):
            before = u.GetClipboardSequenceNumber()
            pyautogui.hotkey(*keys)
            for _ in range(20):
                time.sleep(.05)
                if u.GetClipboardSequenceNumber() != before:
                    last_seq = u.GetClipboardSequenceNumber()
                    text = pyperclip.paste()
                    if text:
                        return text
        return ''
    finally:
        if last_seq is not None and u.GetClipboardSequenceNumber() == last_seq:
            pyperclip.copy(old)


def capture_selection():
    hwnd = u.GetForegroundWindow()
    pid = owner_pid(hwnd)
    if pid == os.getpid():
        return '', None
    text = capture_text()
    if u.GetForegroundWindow() != hwnd:
        raise FlowError('SELECTION_CHANGED', '划词时窗口已变化，请重新选择。')
    return text, {'hwnd': hwnd, 'pid': pid, 'original': text} if text else None


def same_text(left, right):
    return left.replace('\r\n', '\n') == right.replace('\r\n', '\n')


def replace_selection(target, result):
    if not target or not u.IsWindow(target['hwnd']) or owner_pid(target['hwnd']) != target['pid']:
        raise FlowError('SELECTION_CHANGED', '原应用已关闭或变化，未执行替换。请重新划词。')
    hwnd = target['hwnd']
    # Restore only when minimized; ShowWindow(SW_RESTORE) would otherwise unmaximize it.
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)
    u.SetForegroundWindow(hwnd)
    time.sleep(.2)
    if u.GetForegroundWindow() != hwnd:
        raise FlowError('SELECTION_CHANGED', '无法激活原应用，未执行替换。可使用一键复制。')
    current = capture_text()
    if u.GetForegroundWindow() != hwnd or not same_text(current, target['original']):
        raise FlowError('SELECTION_CHANGED', '原选区已变化，未执行替换。请重新划词或使用一键复制。')
    pyperclip.copy(result)
    if u.GetForegroundWindow() != hwnd:
        raise FlowError('SELECTION_CHANGED', '粘贴前窗口已变化，未执行替换。结果已在剪贴板。')
    pyautogui.hotkey('ctrl', 'v')


def startup_command():
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}" --background'
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    return f'"{pythonw}" "{Path(__file__).with_name("app.py")}" --background'


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_NAME)
            return bool(value)
    except OSError:
        return False


def set_startup(enabled):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
