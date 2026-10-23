import base64
import hashlib
import json
import unittest
from unittest.mock import Mock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.gestures import GestureGate,GestureService,checked_landmarks
from dashboard.gesture_routes import install

def hand(kind='point',y=.2):
    p=[[.5,.65,0.] for _ in range(21)];p[0]=[.5,.9,0.]
    for base,pip,tip,x in ((5,6,8,.4),(9,10,12,.5),(13,14,16,.6),(17,18,20,.7)):
        p[base]=[x,.7,0.];p[pip]=[x,.5,0.];p[tip]=[x,.7,0.]
    p[4]=[.2,.6,0.]
    if kind in ('point','pinch','scroll','palm'):p[8]=[.4,y,0.]
    if kind in ('scroll','palm'):p[12]=[.5,.18,0.]
    if kind=='palm':p[16]=[.6,.2,0.];p[20]=[.7,.25,0.]
    if kind=='pinch':p[4]=[.41,y,0.]
    return p

class Gestures(unittest.TestCase):
    def setUp(self):
        # Unit tests must not register real Windows hotkeys or compete with
        # the user's running JARVIS instance.
        guard=patch('core.input_stop.register_stop',return_value=True)
        guard.start();self.addCleanup(guard.stop)
    def test_hotkey_conflict_still_blocks_input(self):
        service=GestureService()
        with patch('core.input_stop.register_stop',return_value=False):
            with self.assertRaisesRegex(ValueError,'already in use'):service.arm('remote',True)
        self.assertFalse(service.control);self.assertEqual(service.mode,'off')
    def test_validation(self):
        for value in (None,{},[],hand()+[[0,0,0]],[[True,0,0]]*21,[[float('nan'),0,0]]*21,[[2,0,0]]*21):
            with self.assertRaises(ValueError):checked_landmarks(value)
    def test_pointer_debounce_and_mirroring(self):
        gate=GestureGate();self.assertEqual(gate.feed(hand(),0),[])
        event=gate.feed(hand(),.2)[0];self.assertEqual(event,{'action':'move','x':.6,'y':.2})
    def test_pinch_once_then_release(self):
        gate=GestureGate();gate.feed(hand('pinch'),0)
        self.assertEqual(gate.feed(hand('pinch'),.2),[{'action':'click'}])
        self.assertEqual(gate.feed(hand('pinch'),2),[])
        gate.feed(hand('palm'),2.1);gate.feed(hand('pinch'),2.2)
        self.assertEqual(gate.feed(hand('pinch'),2.4),[{'action':'click'}])
    def test_open_palm_pauses(self):
        gate=GestureGate();gate.feed(hand('palm'),0);self.assertEqual(gate.feed(hand('palm'),1),[])
    def test_scroll(self):
        gate=GestureGate();gate.feed(hand('scroll'),0);gate.feed(hand('scroll'),.3)
        self.assertEqual(gate.feed(hand('scroll',.1),.4),[{'action':'scroll','amount':3}])
    def test_fist_once_per_hold(self):
        gate=GestureGate();gate.feed(hand('fist'),0)
        self.assertEqual(gate.feed(hand('fist'),.8),[{'action':'media'}])
        self.assertEqual(gate.feed(hand('fist'),5),[])
    def test_preview_never_controls_windows(self):
        service=GestureService();service._apply=Mock();service.arm('remote')
        gen=service.generation;service.feed(hand('pinch'),'remote',gen,0,now=10);service.feed(hand('pinch'),'remote',gen,1,now=10.2)
        service._apply.assert_not_called()
    def test_control_and_stop(self):
        service=GestureService();service._apply=Mock();service.arm('remote',True);gen=service.generation
        service.feed(hand('pinch'),'remote',gen,0,now=10);service.feed(hand('pinch'),'remote',gen,1,now=10.2)
        service._apply.assert_called_once_with({'action':'click'});service.stop()
        with self.assertRaises(ValueError):service.feed(hand(),'remote',gen,2,now=11)
        self.assertFalse(service.control)
    def test_owner_sequence_and_mode(self):
        service=GestureService();service.arm('remote');gen=service.generation
        service.feed(hand(),'remote',gen,10,'a',now=10)
        for source,token,seq,actor in [('pc',gen,11,'a'),('remote','expired',11,'a'),('remote',gen,10,'a'),('remote',gen,11,'b')]:
            with self.assertRaises(ValueError):service.feed(hand(),source,token,seq,actor,now=10.2)
        with self.assertRaises(ValueError):service.arm('remote',True)
    def test_lost_hand_resets_pinch(self):
        service=GestureService();service._apply=Mock();service.arm('remote',True);gen=service.generation
        service.feed(hand('pinch'),'remote',gen,0,now=10)
        service.feed([],'remote',gen,1,now=10.1)
        service.feed(hand('pinch'),'remote',gen,2,now=10.2)
        service._apply.assert_not_called()
    def test_input_exception_disarms(self):
        service=GestureService();service._apply=Mock(side_effect=RuntimeError('failsafe'));service.arm('remote',True);gen=service.generation
        service.feed(hand('pinch'),'remote',gen,0,now=10)
        with self.assertRaises(ValueError):service.feed(hand('pinch'),'remote',gen,1,now=10.2)
        self.assertEqual(service.mode,'off')

class Routes(unittest.TestCase):
    def setUp(self):
        self.service=GestureService();self.service.arm('remote');self.key=hashlib.sha256(b'synthetic session key').digest()
        def decrypt(token,text):
            try:
                blob=base64.b64decode(text,validate=True);return AESGCM(self.key).decrypt(blob[:12],blob[12:],None).decode()
            except Exception:return None
        server=Mock();server._decrypt=decrypt
        app=FastAPI();install(app,server,lambda r:r.headers.get('authorization')=='Bearer synthetic',self.service)
        self.client=TestClient(app);self.headers={'Authorization':'Bearer synthetic'}
    def enc(self,payload):
        import secrets
        nonce=secrets.token_bytes(12)
        return {'enc':base64.b64encode(nonce+AESGCM(self.key).encrypt(nonce,json.dumps(payload).encode(),None)).decode()}
    def test_no_auth(self):
        for path,method in [('/api/gestures/status','get'),('/api/gestures','post'),('/api/gestures/stop','post')]:
            self.assertEqual(getattr(self.client,method)(path).status_code,401)
    def test_encrypted_landmark_to_service(self):
        state=self.client.get('/api/gestures/status',headers=self.headers).json()
        response=self.client.post('/api/gestures',headers=self.headers,json=self.enc({'landmarks':hand(),'generation':state['generation'],'seq':0}))
        self.assertEqual(response.status_code,200);self.assertEqual(self.service.gate.kind,'point')
        self.assertEqual(self.client.post('/api/gestures/stop',headers=self.headers).status_code,200)
        self.assertEqual(self.service.mode,'off')
    def test_reject_plaintext_tamper_large_and_missing_assets(self):
        for body in ({'landmarks':hand()},{'enc':'bad'},[],self.enc({'landmarks':'invalid'})):
            self.assertEqual(self.client.post('/api/gestures',headers=self.headers,json=body).status_code,400)
        self.assertEqual(self.client.post('/api/gestures',headers=self.headers,content='x'*12001).status_code,413)
        self.assertEqual(self.client.get('/gesture-assets/api_keys.json').status_code,404)
    def test_page_and_client_have_no_external_dependencies(self):
        self.assertEqual(self.client.get('/gestures').status_code,200)
        js=self.client.get('/gesture-client.js').text
        self.assertNotIn('https://',js);self.assertIn('visibilitychange',js);self.assertIn('getUserMedia',js)

if __name__=='__main__':unittest.main()
