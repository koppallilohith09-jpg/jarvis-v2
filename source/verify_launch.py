"""Packaged launch evidence and completion speech checks; simulated adapters only."""
import json
from pathlib import Path
import sys
import unittest

import test_launch_confirmation
import test_browser_confirmation
import test_task_announcements
import test_quick_commands


def main():
    modules=(test_launch_confirmation,test_browser_confirmation,
             test_task_announcements,test_quick_commands)
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module)
                             for module in modules)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise RuntimeError('Launch confirmation checks failed.')
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
    report={'passed':True,'tests':result.testsRun,
            'app_evidence':'visible matching windows; simulated Windows adapter',
            'native_browser_evidence':'foreground address URL; simulated accessibility adapter',
            'native_browser_load_verified':False,
            'managed_browser_evidence':'final URL, DOM navigation and HTTP response; simulated Playwright',
            'completion_speech':'local assistant transcript/TTS; mocked speech synthesis',
            'physical_desktop_browser_camera_microphone':'not accessed',
            'live_provider_calls':'not performed'}
    (root/'launch-confirmation-diagnostics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
