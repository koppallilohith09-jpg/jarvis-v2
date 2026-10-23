"""Packaged cloud adapter/form checks. Synthetic key, mocked HTTP only."""
import json,unittest,sys
from pathlib import Path
from test_cloud_connection import Cloud,ConnectionUI,Gemini

def main():
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls) for cls in (Cloud,ConnectionUI,Gemini))
    result=unittest.TextTestRunner().run(suite)
    if not result.wasSuccessful():raise RuntimeError('Cloud adapter/form checks failed.')
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
    (root/'cloud-diagnostics.json').write_text(json.dumps({'mocked_openai_responses':'passed','mocked_native_gemini_stream_and_tools':'passed','gemini_model_list_probe_without_generation':'passed','timeout_recovery':'passed','tool_followup_with_encrypted_reasoning':'passed','masked_key_and_windows_protection':'passed','quota_vs_rate_errors':'passed','live_provider_request':'not performed; requires user key and available provider quota','tests':result.testsRun},indent=2))
if __name__=='__main__':main()
