import ast
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from core import local_privacy as policy, secure_config

ROOT=Path(__file__).resolve().parent

class PrivacyTests(unittest.TestCase):
    def test_remote_ai_and_hosted_speech_rejected(self):
        for url in ('https://api.openai.com/v1','http://192.168.1.3:11434','http://127.0.0.1.evil.example/v1','https://user:password@127.0.0.1/v1'):
            with self.assertRaises(ValueError): policy.validate_provider('openai_compat',{'base_url':url})
        for url in ('http://127.0.0.1:11434/v1','http://localhost:1234/v1','http://[::1]:8080/v1'):
            with self.assertRaises(ValueError):policy.validate_provider('openai_compat',{'base_url':url})
        policy.validate_provider('cloud_setup',{})
        with self.assertRaises(ValueError): policy.validate_provider('whisper',{'backend':'api'})
        with self.assertRaises(ValueError): policy.validate_provider('elevenlabs',{})
        policy.validate_provider('kokoro',{})

    def test_network_policy_rules_without_external_connections(self):
        for event,args in [('socket.getaddrinfo',('example.com',443)),('socket.gethostbyname',('example.com',)),('socket.connect',(None,('8.8.8.8',443))),('socket.sendto',(None,b'data',('10.0.0.1',53)))]:
            with self.assertRaises(PermissionError): policy.audit_network(event,args)
        policy.audit_network('socket.getaddrinfo',('localhost',11434))
        policy.audit_network('socket.connect',(None,('127.0.0.1',11434)))
        policy.audit_network('socket.connect',(None,('::1',11434,0,0)))

    def test_default_local_stack_without_remote_access(self):
        cfg=policy.default_config()
        self.assertFalse(cfg['dashboard_enabled'])
        self.assertEqual(cfg['providers']['pipeline']['llm'],'cloud_setup')
        self.assertEqual(cfg['providers']['pipeline']['tts'],'system_tts')
        self.assertEqual(cfg['providers']['creds']['whisper']['backend'],'local')
        self.assertNotIn('gemini_api_key',cfg)

    @unittest.skipUnless(os.name=='nt','Windows DPAPI test')
    def test_synthetic_credential_round_trip(self):
        data={'gemini_api_key':'SYNTHETIC-NOT-A-REAL-KEY','providers':{'creds':{'a':{'api_key':'another synthetic value'}}},'name':'test'}
        text=secure_config.dumps(data)
        self.assertNotIn('SYNTHETIC-NOT-A-REAL-KEY',text)
        self.assertEqual(secure_config.loads(text),data)

    def test_disabled_plugin_is_not_imported(self):
        source=(ROOT/'core/plugin_loader.py').read_text(encoding='utf-8')
        self.assertLess(source.index('if not get_plugin_enabled(path.stem)'),source.index('spec.loader.exec_module(module)'))

    def test_source_guard_and_cloud_ladder(self):
        source=(ROOT/'main.py').read_text(encoding='utf-8')
        self.assertLess(source.index('install_network_guard()'),source.index('from google import genai'))
        self.assertIn('no offline fallback is permitted',source)
        self.assertIn('Cloud AI is disabled',source)
        source=(ROOT/'core/gemini.py').read_text(encoding='utf-8')
        self.assertIn('ladder = rungs\n    resolved_key = ""',source)

    def test_dashboard_is_opt_in_and_loopback(self):
        source=(ROOT/'dashboard/server.py').read_text(encoding='utf-8')
        self.assertIn("get('dashboard_enabled',False)",source)
        self.assertNotIn('host="0.0.0.0"',source)
        self.assertNotIn('None, _ensure_network_access, PORT, SECURE_PORT)',source)

    def test_all_sources_compile(self):
        for path in ROOT.rglob('*.py'):
            if '.venv' in path.parts: continue
            if any(part in ('build','dist') for part in path.parts):continue
            with self.subTest(path=str(path.relative_to(ROOT))): compile(path.read_text(encoding='utf-8'),str(path),'exec')

if __name__=='__main__': unittest.main()
