import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import core
from prompts import build_prompt
from catalog import MODEL_LABELS, PROVIDERS, normalize_base_url, provider_for_url
import windows_integration as windows
import app
import queue
real_fast_supported = core.r1_fast_supported


def stream(*items):
    return io.BytesIO(b''.join(json.dumps(i).encode() + b'\n' for i in items))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.cancel = threading.Event()
        self.cfg = {'mode': 'local', 'model': 'deepseek-r1:8b'}
        fast = patch('core.r1_fast_supported', return_value=False)
        fast.start()
        self.addCleanup(fast.stop)

    def test_real_stream_protocol(self):
        with patch('core.request', return_value=stream({'response': '<think>hidden</think>'},
                    {'response': 'Hello', 'done': True})), patch('core.event'):
            self.assertEqual(core.infer(self.cfg, 'secret content', '', self.cancel), 'Hello')

    def test_truncated_stream_fails(self):
        with patch('core.request', return_value=stream({'response': 'partial'})):
            with self.assertRaises(core.FlowError) as e:
                core.infer(self.cfg, 'text', '', self.cancel)
            self.assertEqual(e.exception.code, 'NETWORK')

    def test_thinking_only_fails(self):
        with patch('core.request', return_value=stream({'response': '<think>unfinished', 'done': True})):
            with self.assertRaises(core.FlowError) as e:
                core.infer(self.cfg, 'text', '', self.cancel)
            self.assertEqual(e.exception.code, 'EMPTY')

    def test_cancel(self):
        self.cancel.set()
        with self.assertRaises(core.FlowError) as e:
            core.infer(self.cfg, 'text', '', self.cancel)
        self.assertEqual(e.exception.code, 'CANCELLED')

    def test_cloud_http_rejected_before_send(self):
        with self.assertRaises(core.FlowError):
            core.infer({'mode': 'cloud', 'cloud_url': 'http://example.com'}, 'secret', 'key', self.cancel)

    def test_no_key_saved(self):
        with tempfile.TemporaryDirectory() as folder, patch('core.DATA', Path(folder)), patch('core.event'):
            core.save_config(dict(self.cfg, key='SECRET_KEY', cloud_url='https://example.com', cloud_model='x'))
            self.assertNotIn('SECRET_KEY', (Path(folder) / 'settings.json').read_text(encoding='utf-8'))

    def test_log_allowlist(self):
        with tempfile.TemporaryDirectory() as folder, patch('core.DATA', Path(folder)):
            import logging
            log = logging.getLogger('researchflow')
            for h in list(log.handlers):
                h.close()
                log.removeHandler(h)
            core.event('SECRET_KEY / USER CONTENT')
            core.event('INFERENCE_OK')
            for h in log.handlers:
                h.flush()
            value = (Path(folder) / 'diagnostics.log').read_text(encoding='utf-8')
            self.assertNotIn('SECRET', value)
            self.assertNotIn('USER CONTENT', value)
            self.assertIn('INFERENCE_OK', value)
            for h in list(log.handlers):
                h.close()
                log.removeHandler(h)

    def test_recommendations(self):
        self.assertEqual(core.recommend({'ram_gb': 32, 'model_free_gb': 20}), 'deepseek-r1:8b')
        self.assertEqual(core.recommend({'ram_gb': 15.6, 'model_free_gb': 20}), 'deepseek-r1:8b')
        self.assertEqual(core.recommend({'ram_gb': 8, 'model_free_gb': 6}), 'deepseek-r1:1.5b')

    def test_prompt_reuse(self):
        for mode in ('translate', 'explain', 'polish', 'check'):
            self.assertIn('unique text', build_prompt(mode, 'unique text'))

    def test_provision_retry_and_inference(self):
        hw = {'ram_gb': 32, 'model_free_gb': 100, 'system_free_gb': 100,
              'temp_free_gb': 100, 'windows_build': 22631, 'arch': 'AMD64'}
        with patch('core.hardware', return_value=hw), patch('core.ensure_engine'), \
             patch('core.ollama_exe', return_value='ollama.exe'), patch('core.tags', return_value=[]), \
             patch('core.request', side_effect=[OSError('private server response'), stream({'status': 'success'})]) as req, \
             patch('core.infer', return_value='READY') as inference, patch('core.event'):
            core.provision('deepseek-r1:8b', lambda *a: None, self.cancel)
            self.assertEqual(req.call_count, 2)
            inference.assert_called_once()

    def test_disk_fails_before_pull(self):
        hw = {'ram_gb': 32, 'model_free_gb': 1, 'system_free_gb': 100,
              'temp_free_gb': 100, 'windows_build': 22631, 'arch': 'AMD64'}
        with patch('core.hardware', return_value=hw), patch('core.ensure_engine'), \
             patch('core.ollama_exe', return_value='ollama.exe'), patch('core.tags', return_value=[]):
            with self.assertRaises(core.FlowError) as e:
                core.provision('deepseek-r1:8b', lambda *a: None, self.cancel)
            self.assertEqual(e.exception.code, 'DISK')

    def test_invalid_installer_signature_never_runs(self):
        import types
        data = io.BytesIO(b'fake installer')
        data.headers = {'Content-Length': '14'}
        with tempfile.TemporaryDirectory() as folder, patch('core.DATA', Path(folder)), \
             patch('core.tags', side_effect=OSError()), patch('core.ollama_exe', return_value=None), \
             patch('core.urllib.request.urlopen', return_value=data), \
             patch('core.subprocess.run', return_value=types.SimpleNamespace(returncode=1)), \
             patch('core.subprocess.Popen') as launch:
            with self.assertRaises(core.FlowError) as e:
                core.ensure_engine(lambda *a: None, self.cancel)
            self.assertEqual(e.exception.code, 'SIGNATURE')
            launch.assert_not_called()

    def test_low_ram_rejects_before_engine_install(self):
        hw = {'ram_gb': 4, 'model_free_gb': 100, 'system_free_gb': 100,
              'temp_free_gb': 100, 'windows_build': 22631, 'arch': 'AMD64'}
        with patch('core.hardware', return_value=hw), patch('core.ensure_engine') as engine:
            with self.assertRaises(core.FlowError) as e:
                core.provision('deepseek-r1:8b', lambda *a: None, self.cancel)
            self.assertEqual(e.exception.code, 'HARDWARE')
            engine.assert_not_called()

    def test_catalog_sizes_and_custom_provider(self):
        self.assertEqual(len(MODEL_LABELS), 10)
        self.assertTrue(all('约 ' in label for label in MODEL_LABELS.values()))
        self.assertIn('自定义', list(PROVIDERS)[-1])
        self.assertEqual(provider_for_url('https://api.deepseek.com/v1'), 'DeepSeek 官方')
        self.assertIn('自定义', provider_for_url('https://example.com/v1'))

    def test_full_endpoint_normalization(self):
        self.assertEqual(normalize_base_url(' https://example.com/v1/chat/completions/ '), 'https://example.com/v1')

    def test_preferences_persist_without_key(self):
        with tempfile.TemporaryDirectory() as folder, patch('core.DATA', Path(folder)), patch('core.event'):
            cfg = core.load_config()
            cfg.update(autostart=True, auto_hide=True, key='NEVER_SAVE')
            core.save_config(cfg)
            saved = core.load_config()
            self.assertTrue(saved['autostart'])
            self.assertTrue(saved['auto_hide'])
            self.assertNotIn('NEVER_SAVE', (Path(folder) / 'settings.json').read_text(encoding='utf-8'))

    def test_length_limit_blocks_success(self):
        with patch('core.request', return_value=stream({'response': 'unfinished', 'done': True, 'done_reason': 'length'})):
            with self.assertRaises(core.FlowError) as e:
                core.infer(self.cfg, 'text', '', self.cancel)
            self.assertEqual(e.exception.code, 'LIMIT')

    def test_correction_only_text_prompt(self):
        prompt = build_prompt('check', 'We has a result.')
        self.assertIn('ONLY the corrected text', prompt)
        self.assertNotIn('Issues found:', prompt)

    def test_replacement_refuses_changed_selection(self):
        target = {'hwnd': 42, 'pid': 7, 'original': 'original'}
        with patch.object(windows.u, 'IsWindow', return_value=1), patch.object(windows.u, 'IsIconic', return_value=0), \
             patch.object(windows.u, 'GetForegroundWindow', return_value=42), \
             patch.object(windows.u, 'SetForegroundWindow'), patch('windows_integration.owner_pid', return_value=7), \
             patch('windows_integration.capture_text', return_value='changed'), patch('windows_integration.time.sleep'), \
             patch('windows_integration.pyautogui.hotkey') as paste:
            with self.assertRaises(core.FlowError):
                windows.replace_selection(target, 'result')
            paste.assert_not_called()

    def test_replacement_copies_and_pastes_only_matching_selection(self):
        target = {'hwnd': 42, 'pid': 7, 'original': 'original'}
        with patch.object(windows.u, 'IsWindow', return_value=1), patch.object(windows.u, 'IsIconic', return_value=0), \
             patch.object(windows.u, 'GetForegroundWindow', return_value=42), \
             patch.object(windows.u, 'SetForegroundWindow'), patch('windows_integration.owner_pid', return_value=7), \
             patch('windows_integration.capture_text', return_value='original'), patch('windows_integration.time.sleep'), \
             patch('windows_integration.pyperclip.copy') as copy, patch('windows_integration.pyautogui.hotkey') as paste:
            windows.replace_selection(target, 'result')
            copy.assert_called_once_with('result')
            paste.assert_called_once_with('ctrl', 'v')

    def test_replacement_refuses_closed_window(self):
        with patch.object(windows.u, 'IsWindow', return_value=0), patch('windows_integration.pyautogui.hotkey') as paste:
            with self.assertRaises(core.FlowError):
                windows.replace_selection({'hwnd': 42, 'pid': 7, 'original': 'text'}, 'result')
            paste.assert_not_called()

    def test_startup_registers_quoted_background_command(self):
        with patch('windows_integration.winreg.CreateKeyEx') as create, \
             patch('windows_integration.winreg.SetValueEx') as write, \
             patch('windows_integration.startup_command', return_value='"C:\\A B\\ResearchFlowAI.exe" --background'):
            windows.set_startup(True)
            self.assertEqual(write.call_args.args[-1], '"C:\\A B\\ResearchFlowAI.exe" --background')

    def test_startup_disable_removes_only_own_value(self):
        with patch('windows_integration.winreg.CreateKeyEx'), patch('windows_integration.winreg.DeleteValue') as delete:
            windows.set_startup(False)
            self.assertEqual(delete.call_args.args[-1], 'ResearchFlowAI')

    def test_fast_r1_only_with_verified_template(self):
        with patch('core.r1_fast_supported', return_value=True):
            payload = core.local_payload('deepseek-r1:8b', 'Fixture text')
            self.assertTrue(payload['raw'])
            self.assertIn('</think>', payload['prompt'])
            self.assertIn('Fixture text', payload['prompt'])
        with patch('core.r1_fast_supported', return_value=False):
            payload = core.local_payload('qwen2.5:3b', 'Fixture text')
            self.assertNotIn('raw', payload)
            self.assertEqual(payload['prompt'], 'Fixture text')

    def test_shortcut_conflict_uses_backup(self):
        a = app.App.__new__(app.App)
        a.q = queue.Queue()
        with patch.object(windows.u, 'RegisterHotKey', side_effect=[False, True]), \
             patch.object(windows.u, 'GetMessageW', return_value=0), \
             patch.object(windows.u, 'UnregisterHotKey'), patch('app.event'):
            a.hotkeys()
        self.assertTrue(a.hotkey_ready)
        self.assertEqual(a.q.get_nowait(), ('hotkey_active', 'Ctrl+Alt+R'))

    def test_all_shortcuts_conflict_fails_cleanly(self):
        a = app.App.__new__(app.App)
        a.q = queue.Queue()
        with patch.object(windows.u, 'RegisterHotKey', return_value=False), patch('app.event'):
            a.hotkeys()
        self.assertEqual(a.q.get_nowait()[0], 'hotkey')

    def test_fast_template_probe(self):
        real_fast_supported.cache_clear()
        with patch('core.request', return_value=io.BytesIO(json.dumps({'template': '<｜User｜><｜Assistant｜></think> bos_token', 'model_info': {'general.architecture': 'qwen3'}}).encode())):
            self.assertTrue(real_fast_supported('deepseek-r1:8b'))
        with patch('core.request', return_value=io.BytesIO(json.dumps({'template': '<｜User｜><｜Assistant｜></think> bos_token', 'model_info': {'general.architecture': 'qwen2'}}).encode())):
            self.assertFalse(real_fast_supported('deepseek-r1:1.5b'))
        with patch('core.request', side_effect=OSError()):
            self.assertFalse(real_fast_supported('deepseek-r1:7b'))
        self.assertFalse(real_fast_supported('qwen2.5:7b'))
        real_fast_supported.cache_clear()


if __name__ == '__main__':
    unittest.main(verbosity=2)
