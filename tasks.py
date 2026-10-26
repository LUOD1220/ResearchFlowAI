"""Task-level presentation and validation; never log selected text."""
import re
from core import FlowError, infer, event, check_cancel
from prompts import build_prompt


def plain_explanation(text):
    # Protect code: exponent operators such as x**2 are meaningful content.
    pieces = re.split(r'(```[\s\S]*?(?:```|$)|`[^`\n]+`)', text)
    result = []
    for part in pieces:
        if part.startswith('```'):
            code = re.sub(r'^```[^\n]*\n?', '', part)
            result.append(re.sub(r'```$', '', code))
        elif part.startswith('`') and part.endswith('`'):
            result.append(part[1:-1])
        else:
            part = re.sub(r'\*\*(.+?)\*\*', lambda m: m.group(1), part, flags=re.S)
            part = re.sub(r'__(.+?)__', lambda m: m.group(1), part, flags=re.S)
            part = re.sub(r'(?m)^\s{0,3}#{1,6}\s+', '', part)
            # Partial streamed opening markers should not flash in headings.
            part = re.sub(r'(?m)^(\s*)\*\*', r'\1', part)
            result.append(part)
    return ''.join(result).strip()


def is_edit_refusal(text):
    value = text.strip().replace('’', "'").lower()
    if len(value) > 1500:
        return False
    return bool(re.match(
        r"^(?:(?:i(?:'m| am)\s+sorry|sorry)[,.:!\s]*(?:but\s+)?)?"
        r"(?:i\s+(?:cannot|can not|can't|am unable to)\s+(?:answer|assist|help|comply|provide|process|engage|participate|respond|discuss|fulfill)|"
        r"(?:抱歉|对不起)[，,：:\s]*(?:我)?(?:无法|不能|不可以))", value))


def invalid_edit(answer, original):
    if is_edit_refusal(answer) and not is_edit_refusal(original):
        return True
    return any(marker in answer and marker not in original for marker in (
        '<quoted_text>', '</quoted_text>', 'You are proofreading a quotation',
        'Return ONLY the corrected text', 'Quoted text to proofread:'))


def run_task(config, mode, text, key, cancel, on_text=None, progress=None):
    # Proofreading is validated as a whole: a refusal must never become a
    # streaming, copyable replacement of the user's original selection.
    callback = None if mode == 'check' else on_text
    if mode == 'explain' and callback:
        callback = lambda value: on_text(plain_explanation(value))
    answer = infer(config, build_prompt(mode, text), key, cancel, callback)
    if mode == 'check' and invalid_edit(answer, text):
        check_cancel(cancel)
        if progress:
            progress('模型未完成校对，正在重新确认一次纠错任务…')
        event('EDIT_RETRY')
        # Clarify the same editing task once; do not switch providers/models or
        # reinterpret a refusal as a successful correction.
        answer = infer(config, build_prompt('check_retry', text), key, cancel)
        if invalid_edit(answer, text):
            raise FlowError('EDIT_REFUSAL', '模型未能完成这段文字的纠错，原文未替换。请重试或选择其他模型。')
    return plain_explanation(answer) if mode == 'explain' else answer
