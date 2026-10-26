"""macOS adapter logic with fake frameworks. NOT a native Mac integration test."""
import importlib.util
import plistlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import core


def adapter():
    appkit = types.ModuleType('AppKit')
    for name in ('NSWorkspace', 'NSRunningApplication', 'NSPasteboard', 'NSStatusBar', 'NSMenu', 'NSMenuItem'):
        setattr(appkit, name, MagicMock())
    appkit.NSApplicationActivateIgnoringOtherApps = 2
    appkit.NSVariableStatusItemLength = -1
    foundation = types.ModuleType('Foundation'); foundation.NSObject = object
    objc = types.ModuleType('objc'); objc.IBAction = lambda f: f
    services = types.ModuleType('ApplicationServices')
    for name in ('AXIsProcessTrusted', 'AXUIElementCreateApplication', 'AXUIElementCopyAttributeValue', 'AXUIElementPerformAction'):
        setattr(services, name, MagicMock())
    cf = types.ModuleType('CoreFoundation'); cf.CFEqual = lambda a,b: a==b
    modules = {'AppKit':appkit,'Foundation':foundation,'objc':objc,'ApplicationServices':services,
               'CoreFoundation':cf,'Quartz':MagicMock(),'pyautogui':MagicMock(),'pyperclip':MagicMock()}
    spec = importlib.util.spec_from_file_location('_researchflow_mac_test', Path(__file__).with_name('macos_integration.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class MacContractTests(unittest.TestCase):
    def setUp(self):
        self.m = adapter()
        self.target = {'pid':7,'bundle':'test.editor','window':'window-A','original':'original'}
        self.native = MagicMock()
        self.native.isTerminated.return_value = False
        self.native.bundleIdentifier.return_value = 'test.editor'
        self.m.NSRunningApplication.runningApplicationWithProcessIdentifier_.return_value = self.native

    def test_login_plist_create_remove(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(self.m,'AGENT',Path(folder)/'test.plist'), patch.object(sys,'frozen',True,create=True):
            self.m.set_startup(True)
            data = plistlib.loads(self.m.AGENT.read_bytes())
            self.assertTrue(data['RunAtLoad']); self.assertFalse(data['KeepAlive'])
            self.assertEqual(data['ProgramArguments'][-1], '--background')
            self.assertTrue(self.m.startup_enabled())
            self.m.set_startup(False)
            self.assertFalse(self.m.startup_enabled())

    def test_closed_app_refuses_replacement(self):
        self.m.NSRunningApplication.runningApplicationWithProcessIdentifier_.return_value = None
        with self.assertRaises(core.FlowError):self.m.replace_selection(self.target,'result')
        self.m.pyautogui.hotkey.assert_not_called()

    def test_other_window_in_same_app_refuses(self):
        with patch.object(self.m,'front_app',return_value=(self.native,7)),patch.object(self.m,'focused_window',return_value='window-B'),patch.object(self.m.time,'sleep'):
            with self.assertRaises(core.FlowError):self.m.replace_selection(self.target,'result')
        self.m.pyautogui.hotkey.assert_not_called()

    def test_changed_selection_refuses(self):
        with patch.object(self.m,'front_app',return_value=(self.native,7)),patch.object(self.m,'focused_window',return_value='window-A'),patch.object(self.m,'capture_text',return_value='changed'),patch.object(self.m.time,'sleep'):
            with self.assertRaises(core.FlowError):self.m.replace_selection(self.target,'result')
        self.m.pyautogui.hotkey.assert_not_called()

    def test_matching_selection_uses_command_v(self):
        with patch.object(self.m,'front_app',return_value=(self.native,7)),patch.object(self.m,'focused_window',return_value='window-A'),patch.object(self.m,'capture_text',return_value='original'),patch.object(self.m.time,'sleep'):
            self.m.replace_selection(self.target,'result')
        self.m.pyperclip.copy.assert_called_once_with('result')
        self.m.pyautogui.hotkey.assert_called_once_with('command','v')

    def test_permission_preflight(self):
        self.m.AXIsProcessTrusted.return_value = False
        self.assertFalse(self.m.permission_status())


if __name__=='__main__': unittest.main(verbosity=2)
