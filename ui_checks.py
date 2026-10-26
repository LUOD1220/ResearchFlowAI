"""Component tests: no network, registry mutation or external keyboard injection."""
import json
from pathlib import Path
import sys
import tkinter as tk
import time
from unittest.mock import patch
import app
from catalog import CUSTOM_PROVIDER
from appearance import THEMES, DEFAULT_THEME
from core import FlowError


def run(report_path):
    root = tk.Tk()
    a = app.App(root, test_mode=True)
    root.geometry('740x650')
    root.update()
    checks = {}
    try:
        a.key.set('FAKE-KEY')
        a.cloud_consent.set(True)
        a.provider.set('硅基流动 SiliconFlow')
        a.provider_changed()
        checks['provider_sets_url'] = a.cloud_url.get() == 'https://api.siliconflow.cn/v1'
        checks['provider_clears_key_consent'] = not a.key.get() and not a.cloud_consent.get()
        a.provider.set(CUSTOM_PROVIDER)
        a.provider_changed()
        a.cloud_url.set('https://example.com/v1')
        a.cloud_model.set('my-actual-model-id')
        checks['custom_address_model'] = a.snapshot()['cloud_model'] == 'my-actual-model-id'
        a.key.set('FAKE-KEY')
        a.cloud_consent.set(True)
        a.cloud_url.set('https://another.example/v1')
        checks['endpoint_change_clears_key_consent'] = not a.key.get() and not a.cloud_consent.get()
        target = {'hwnd': 42, 'pid': 7, 'original': 'Fixture original'}
        a.q.put(('selection', ('Fixture original', target)))
        a.drain(); root.update()
        checks['selection_workflow'] = a.book.index(a.book.select()) == 0 and a.input.get('1.0', 'end-1c') == 'Fixture original'
        for mode in ('translate', 'polish', 'check', 'explain'):
            a.q.put(('complete', ('Fixture result', mode, 'Fixture original', target)))
            a.drain(); root.update()
            checks[f'{mode}_copy_enabled'] = 'disabled' not in a.copy_button.state()
            checks[f'{mode}_replace_enabled'] = ('disabled' not in a.replace_button.state()) == (mode != 'explain')
        checks['result_actions_visible_at_minimum_size'] = bool(a.copy_button.winfo_ismapped() and a.replace_button.winfo_ismapped())
        checks['result_area_readable_at_minimum_size'] = a.output.winfo_height() >= 60
        a.q.put(('complete', ('Fixture result', 'check', 'Fixture original', target)))
        a.drain()
        a.input.insert('end', ' changed')
        with patch('app.replace_selection') as replace:
            a.replace()
            checks['modified_input_blocks_replace'] = not replace.called
        a.popup_mode = True
        a.auto_hide.set(True)
        a.ignore_hide_until = 0
        with patch('app.foreground_is_ours', return_value=False):
            a.watch_focus()
        checks['auto_hide'] = root.state() == 'withdrawn'
        a.show(); root.update()
        a.popup_mode = True
        a.auto_hide.set(False)
        with patch('app.foreground_is_ours', return_value=False):
            a.watch_focus()
        checks['auto_hide_off_keeps_visible'] = root.state() == 'normal'
        with patch('app.load_config', return_value={'configured': False, 'model': 'old'}), patch('app.save_config') as saved:
            a.save_preferences()
            checks['preferences_do_not_mark_model_configured'] = saved.call_args.args[0]['configured'] is False
        import tempfile
        with tempfile.TemporaryDirectory() as folder, patch('app.DATA', Path(folder)):
            (Path(folder) / 'settings.json').write_text('{}')
            a.background = True
            a.config['configured'] = False
            a.initial_visibility()
            checks['unconfigured_start_stays_visible'] = root.state() == 'normal'
            a.config['configured'] = True
            a.initial_visibility()
            checks['background_start_hides'] = root.state() == 'withdrawn'
            a.show(); root.update()
            checks['hidden_window_can_reopen'] = root.state() == 'normal'
        a.book.select(a.setup_page); root.update()
        checks['footer_visible'] = a.bar.winfo_rooty() - root.winfo_rooty() + a.bar.winfo_height() < root.winfo_height()
        a.clear()
        checks['clear_invalidates_result'] = not a.result_ready and a.source_target is None
        a.book.select(a.preferences_page); root.update()
        a.theme.set('深色 · 石墨'); a.opacity.set(85); a.preview_appearance(); root.update()
        checks['dark_theme_applied'] = a.output.cget('background') == THEMES['深色 · 石墨']['surface']
        checks['opacity_preview'] = abs(float(root.attributes('-alpha'))-.85) < .01
        a.reset_appearance(); root.update()
        checks['appearance_reset'] = a.theme.get() == DEFAULT_THEME and float(root.attributes('-alpha')) == 1
        a.book.select(a.work); a.mode.set('local')
        a.input.insert('1.0', 'We has results.')
        with patch('app.run_task', side_effect=FlowError('EDIT_REFUSAL', '模型未完成纠错，原文未替换。')):
            a.process('check')
            deadline = time.monotonic()+3
            while a.busy and time.monotonic() < deadline:
                root.update(); time.sleep(.02)
        checks['refusal_not_copyable'] = not a.result_ready and 'disabled' in a.copy_button.state()
        checks['refusal_not_replaceable'] = 'disabled' in a.replace_button.state()
        checks['refusal_has_no_fake_output'] = not a.output.get('1.0', 'end-1c')
    finally:
        a.close()
    Path(report_path).write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    assert all(checks.values()), checks
    print(f'{len(checks)} GUI component checks passed')


if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else 'ui-component-results.json')
