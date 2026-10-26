"""Native macOS foreground-app, selection, paste, menu bar and login integration."""
import os
from pathlib import Path
import plistlib
import sys
import time
import subprocess
import pyautogui
import pyperclip
import objc
from AppKit import (NSWorkspace, NSRunningApplication, NSApplicationActivateIgnoringOtherApps,
                    NSPasteboard, NSStatusBar, NSVariableStatusItemLength, NSMenu, NSMenuItem)
from Foundation import NSObject
from ApplicationServices import (AXIsProcessTrusted, AXUIElementCreateApplication,
                                 AXUIElementCopyAttributeValue, AXUIElementPerformAction)
from CoreFoundation import CFEqual
import Quartz
from core import FlowError

AGENT = Path.home() / 'Library/LaunchAgents/com.researchflowai.desktop.plist'


def permission_status():
    return bool(AXIsProcessTrusted()) and bool(getattr(Quartz, 'CGPreflightListenEventAccess', lambda: True)())


def open_permission_settings():
    subprocess.Popen(['/usr/bin/open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'])


def front_app():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app, int(app.processIdentifier()) if app else None


def foreground_is_ours():
    return front_app()[1] == os.getpid()


def focused_window(pid):
    try:
        error, window = AXUIElementCopyAttributeValue(AXUIElementCreateApplication(pid), 'AXFocusedWindow', None)
        return window if error == 0 else None
    except Exception:
        return None


def same_window(left, right):
    return left is not None and right is not None and bool(CFEqual(left, right))


def bring_to_front():
    NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)


def capture_text():
    if not AXIsProcessTrusted():
        raise FlowError('PERMISSION', '请在 macOS 系统设置中为 ResearchFlow AI 开启“辅助功能”；全局快捷键还需要“输入监控”。')
    mask = Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskAlternate | Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskShift
    for _ in range(100):
        if not Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateCombinedSessionState) & mask:
            break
        time.sleep(.02)
    else:
        return ''
    board = NSPasteboard.generalPasteboard()
    old = pyperclip.paste()
    before = int(board.changeCount())
    last = None
    try:
        pyautogui.hotkey('command', 'c')
        for _ in range(30):
            time.sleep(.05)
            if int(board.changeCount()) != before:
                last = int(board.changeCount())
                value = pyperclip.paste()
                if value:
                    return value
        return ''
    finally:
        if last is not None and int(board.changeCount()) == last:
            pyperclip.copy(old)


def capture_selection():
    app, pid = front_app()
    if not app or pid == os.getpid():
        return '', None
    bundle = str(app.bundleIdentifier() or '')
    window = focused_window(pid)
    text = capture_text()
    if front_app()[1] != pid or (window is not None and not same_window(window, focused_window(pid))):
        raise FlowError('SELECTION_CHANGED', '获取选区时前台应用发生变化，请重新划词。')
    return text, {'pid': pid, 'bundle': bundle, 'window': window, 'original': text} if text and window is not None else None


def same_text(left, right):
    return left.replace('\r\n', '\n') == right.replace('\r\n', '\n')


def replace_selection(target, result):
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(target['pid']) if target else None
    if not app or app.isTerminated() or str(app.bundleIdentifier() or '') != target['bundle']:
        raise FlowError('SELECTION_CHANGED', '原应用已关闭或变化，未执行替换。')
    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    if target.get('window') is None:
        raise FlowError('SELECTION_CHANGED', '未取得原窗口的辅助功能引用，未执行替换。')
    AXUIElementPerformAction(target['window'], 'AXRaise')
    time.sleep(.3)
    if front_app()[1] != target['pid'] or not same_window(target['window'], focused_window(target['pid'])):
        raise FlowError('SELECTION_CHANGED', '无法激活原应用，未执行替换。')
    current = capture_text()
    if (front_app()[1] != target['pid'] or not same_window(target['window'], focused_window(target['pid']))
            or not same_text(current, target['original'])):
        raise FlowError('SELECTION_CHANGED', '原选区已变化，未执行替换。请重新划词或使用一键复制。')
    pyperclip.copy(result)
    if front_app()[1] != target['pid'] or not same_window(target['window'], focused_window(target['pid'])):
        raise FlowError('SELECTION_CHANGED', '粘贴前应用已变化，未执行替换。')
    pyautogui.hotkey('command', 'v')


def startup_enabled():
    return AGENT.is_file()


def set_startup(enabled):
    if not enabled:
        AGENT.unlink(missing_ok=True)
        return
    args = [sys.executable, '--background'] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).with_name('app.py')), '--background']
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    temp = AGENT.with_suffix('.tmp')
    temp.write_bytes(plistlib.dumps({'Label': 'com.researchflowai.desktop', 'ProgramArguments': args,
                                    'RunAtLoad': True, 'KeepAlive': False, 'LimitLoadToSessionType': 'Aqua'}))
    temp.replace(AGENT)


class MenuDelegate(NSObject):
    @objc.IBAction
    def openAction_(self, sender):
        self.queue.put(('show', None))
    @objc.IBAction
    def hideAction_(self, sender):
        self.queue.put(('hide', None))
    @objc.IBAction
    def quitAction_(self, sender):
        self.queue.put(('exit', None))


class MacTray:
    def __init__(self, queue):
        self.delegate = MenuDelegate.alloc().init()
        self.delegate.queue = queue
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.item.button().setTitle_('RF')
        self.item.button().setToolTip_('ResearchFlow AI')
        self.menu = NSMenu.alloc().initWithTitle_('ResearchFlow AI')
        for title, action in (('打开 ResearchFlow AI', 'openAction:'), ('隐藏', 'hideAction:'), ('退出', 'quitAction:')):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, '')
            item.setTarget_(self.delegate)
            self.menu.addItem_(item)
        self.item.setMenu_(self.menu)
    def stop(self):
        NSStatusBar.systemStatusBar().removeStatusItem_(self.item)


def run_single_instance(factory, background):
    import fcntl
    import uuid
    import core
    core.DATA.mkdir(parents=True, exist_ok=True)
    lock = (core.DATA / 'instance.lock').open('a')
    signal = core.DATA / 'show-request'
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        signal.write_text(uuid.uuid4().hex)
        lock.close()
        return
    previous = signal.read_text() if signal.exists() else ''
    app = factory(background)
    def poll():
        nonlocal previous
        try:
            current = signal.read_text() if signal.exists() else ''
            if current != previous:
                previous = current
                app.show()
        except OSError:
            pass
        app.root.after(300, poll)
    app.root.after(300, poll)
    try:
        app.root.mainloop()
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
