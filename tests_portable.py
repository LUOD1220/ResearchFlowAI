"""Portable logic checks; no network, permissions or external keyboard input."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import core
import tasks
from appearance import valid_opacity, THEMES
from prompts import build_prompt
import macos_support


class PortableTests(unittest.TestCase):
    def test_polish_language_drift_retry(self):
        source = 'May I ask the time about next midterm and the final exam for CHM 1311F, cause I maybe leave ottawa for three weeks, I can arrange my time reasonably according to the TA working time.'
        polish = 'Miejsce, czy chcesz powiedzieć o czasach z czwartej medyzy i z egzaminu, co wypłynąć, jeśli chcesz zastąpić wodzę w trzech zmiennikach.'
        good = 'Could you let me know when the next midterm and final exam for CHM 1311F will take place? I may be away from Ottawa for three weeks, so I would like to plan my schedule around the TA working hours.'
        self.assertTrue(tasks.obvious_language_drift(source, polish))
        self.assertFalse(tasks.obvious_language_drift(source, good))
        with patch('tasks.infer', side_effect=[polish, good]) as infer, patch('tasks.event'):
            self.assertEqual(tasks.run_task({}, 'polish', source, '', threading.Event()), good)
            self.assertEqual(infer.call_count, 2)
            self.assertIsNone(infer.call_args_list[0].args[4])
        with patch('tasks.infer', return_value=polish), patch('tasks.event'):
            with self.assertRaises(core.FlowError):
                tasks.run_task({}, 'polish', source, '', threading.Event())

    def test_plain_explanation(self):
        raw = '**解释内容： **\n\n**摘要说明：**\n普通段落，**关键术语**。\n### 示例\n解释。'
        actual = tasks.plain_explanation(raw)
        self.assertNotIn('**', actual)
        self.assertNotIn('###', actual)
        self.assertIn('关键术语', actual)

    def test_code_exponents_are_content(self):
        self.assertIn('x**2', tasks.plain_explanation('**代码**：`x**2`'))
        self.assertIn('x**2', tasks.plain_explanation('```python\nx**2\n```'))
        self.assertEqual(tasks.plain_explanation('x**2'), 'x**2')

    def test_explanation_prompt_plain_factual(self):
        prompt = build_prompt('explain', 'sample')
        self.assertIn('不要使用 Markdown', prompt)
        self.assertIn('不要把原文没有的', prompt)

    def test_refusal_detection(self):
        self.assertTrue(tasks.is_edit_refusal("I'm sorry, I cannot answer that question."))
        self.assertTrue(tasks.is_edit_refusal('I am sorry, but I cannot assist with that.'))
        self.assertTrue(tasks.is_edit_refusal('抱歉，我无法回答。'))
        self.assertTrue(tasks.is_edit_refusal('I am sorry, but I cannot engage in discussions about this topic.'))
        self.assertFalse(tasks.is_edit_refusal('We have tested the method.'))

    def test_prompt_echo_not_a_correction(self):
        with patch('tasks.infer', return_value='You are proofreading a quotation.\n<quoted_text>'), patch('tasks.event'):
            with self.assertRaises(core.FlowError):
                tasks.run_task({}, 'check', 'We has results.', '', threading.Event())

    def test_refusal_retry_then_success(self):
        with patch('tasks.infer', side_effect=["I'm sorry, I cannot answer that question.", 'We have results.']) as infer, patch('tasks.event'):
            out = tasks.run_task({'mode': 'local'}, 'check', 'We has results.', '', threading.Event())
            self.assertEqual(out, 'We have results.')
            self.assertEqual(infer.call_count, 2)
            self.assertNotEqual(infer.call_args_list[0].args[1], infer.call_args_list[1].args[1])

    def test_persistent_refusal_is_error_not_replacement(self):
        with patch('tasks.infer', return_value="I'm sorry, I cannot answer that question.") as infer, patch('tasks.event'):
            with self.assertRaises(core.FlowError) as e:
                tasks.run_task({}, 'check', 'We has results.', '', threading.Event())
            self.assertEqual(e.exception.code, 'EDIT_REFUSAL')
            self.assertEqual(infer.call_count, 2)

    def test_proofreading_a_refusal_sentence_is_allowed(self):
        text = 'I cannot answer that question.'
        with patch('tasks.infer', return_value=text) as infer:
            self.assertEqual(tasks.run_task({}, 'check', text, '', threading.Event()), text)
            self.assertEqual(infer.call_count, 1)

    def test_no_check_partial_output(self):
        output = []
        with patch('tasks.infer', return_value='We have results.') as infer:
            tasks.run_task({}, 'check', 'We has results.', '', threading.Event(), output.append)
            self.assertIsNone(infer.call_args.args[4])
            self.assertFalse(output)

    def test_explanation_final_sanitized(self):
        with patch('tasks.infer', return_value='**主题**\n解释'):
            self.assertEqual(tasks.run_task({}, 'explain', 'text', '', threading.Event()), '主题\n解释')

    def test_cancelled_retry_is_not_sent(self):
        cancelled = threading.Event(); cancelled.set()
        with patch('tasks.infer', return_value="I'm sorry, I cannot answer that question.") as infer:
            with self.assertRaises(core.FlowError):
                tasks.run_task({}, 'check', 'We has results.', '', cancelled)
            self.assertEqual(infer.call_count, 1)

    def test_opacity_bounds(self):
        self.assertEqual(valid_opacity(.1), .7)
        self.assertEqual(valid_opacity(2), 1)
        self.assertEqual(valid_opacity('bad'), 1)
        self.assertEqual(valid_opacity(.85), .85)
        self.assertEqual(len(THEMES), 4)

    def test_appearance_saved_with_existing_fields(self):
        with tempfile.TemporaryDirectory() as d, patch('core.DATA', Path(d)), patch('core.event'):
            cfg = core.load_config(); cfg.update(model='deepseek-r1:8b', theme='深色 · 石墨', opacity=.85)
            core.save_config(cfg)
            saved = core.load_config()
            self.assertEqual((saved['theme'], saved['opacity'], saved['model']), ('深色 · 石墨', .85, 'deepseek-r1:8b'))

    def test_macos_hardware_parsing_with_fixture(self):
        def command(args, timeout=20):
            return '17179869184' if args[-1]=='hw.memsize' else 'Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 100.\nPages inactive: 200.\nPages speculative: 50.'
        with patch('macos_support.command', side_effect=command), patch('macos_support.platform.machine', return_value='arm64'), patch('macos_support.platform.mac_ver', return_value=('14.7', (), '')), patch('core.disk_free', return_value=100):
            hw = macos_support.mac_hardware()
            self.assertEqual(hw['ram_gb'], 16)
            self.assertEqual(hw['arch'], 'arm64')
            self.assertEqual(hw['macos_version'], '14.7')


if __name__ == '__main__':
    unittest.main(verbosity=2)
