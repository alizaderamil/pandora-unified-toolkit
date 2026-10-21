"""Offline regression tests: no Tk window, USB device or subprocess required."""
import unittest
from unittest.mock import MagicMock, patch

import pandora_unified as app


class RelockReferenceTests(unittest.TestCase):
    def test_open_and_all_buttons_are_read_only_for_every_profile_and_language(self):
        previous = app._CURRENT_LANG
        try:
            for language in ('en', 'ru', 'az'):
                app.set_lang(language)
                for profile in [None, *app.DEVICE_PROFILES.values()]:
                    with self.subTest(language=language, profile=(profile or {}).get('codename')):
                        instance = app.App.__new__(app.App)
                        instance.root = MagicMock()
                        instance.device_profile = profile
                        instance._ensure_profile = MagicMock(side_effect=AssertionError('device probe'))
                        with patch.object(app.tk, 'Toplevel') as window, \
                             patch.object(app.ttk, 'Frame'), \
                             patch.object(app.ttk, 'Label'), \
                             patch.object(app.ttk, 'Button') as button, \
                             patch.object(app.scrolledtext, 'ScrolledText') as text, \
                             patch.object(app.subprocess, 'run', side_effect=AssertionError('process')), \
                             patch.object(app.Path, 'write_text', side_effect=AssertionError('file write')):
                            instance.action_lock_wizard()
                            self.assertEqual(button.call_count, 1)
                            button.call_args.kwargs['command']()
                            window.return_value.destroy.assert_called_once()
                            body = text.return_value.insert.call_args.args[1]
                            self.assertNotEqual(body, 'lock.review.body')
                            self.assertIn('rollback', body)
                            text.return_value.configure.assert_called_with(state='disabled')
                            instance._ensure_profile.assert_not_called()
        finally:
            app.set_lang(previous)

    def test_reference_translations_exist_without_fallback(self):
        for language in ('en', 'ru', 'az'):
            for key in ('lock.review.title', 'lock.review.body', 'lock.review.close'):
                self.assertTrue(app.TRANSLATIONS[language][key])


if __name__ == '__main__':
    unittest.main()
