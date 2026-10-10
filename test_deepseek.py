import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import deepseek

class DeepSeekTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.cfg=patch.object(deepseek,'CONFIG_PATH',Path(self.tmp.name)/'.local-model.json');self.cfg.start()
        self.env=patch.dict(deepseek.os.environ,{},clear=True);self.env.start()
    def tearDown(self):
        self.env.stop();self.cfg.stop();self.tmp.cleanup()
    def test_defaults_and_missing_key(self):
        self.assertEqual(deepseek.settings()['model'],'deepseek-flash')
        self.assertFalse(deepseek.public_settings()['configured'])
        with self.assertRaisesRegex(ValueError,'密钥'): deepseek.request('/models')
    def test_save_and_no_secret_in_public_state(self):
        data=deepseek.save_settings({'key':'test-secret-only','model':'deepseek-flash'})
        self.assertNotIn('test-secret-only',json.dumps(data))
        self.assertEqual(deepseek.settings()['key'],'test-secret-only')
        self.assertTrue(deepseek.public_settings()['configured'])
    def test_environment_priority(self):
        deepseek.save_settings({'key':'local-test-key'})
        with patch.dict(deepseek.os.environ,{'DEEPSEEK_API_KEY':'env-test-key'}):
            self.assertEqual(deepseek.settings()['key'],'env-test-key')
            with self.assertRaises(ValueError): deepseek.save_settings({'key':'new-key'})
    def test_reject_bad_settings(self):
        for d in [{'key':''},{'key':'abc\ndef'},{'key':'abc','model':'bad model'}]:
            with self.assertRaises(ValueError): deepseek.save_settings(d)
    def test_http_error_redacted(self):
        deepseek.save_settings({'key':'private-test-key'})
        with patch('urllib.request.OpenerDirector.open',side_effect=urllib.error.HTTPError('https://api.deepseek.com',401,'private-test-key',{},None)):
            with self.assertRaisesRegex(ValueError,'401') as exc: deepseek.request('/models')
            self.assertNotIn('private-test-key',str(exc.exception))
    def test_models_check(self):
        with patch('deepseek.request',return_value={'data':[{'id':'deepseek-flash'}]}):
            self.assertTrue(deepseek.test_connection()['ok'])
        with patch('deepseek.request',return_value={'data':[{'id':'different'}]}):
            with self.assertRaisesRegex(ValueError,'可用模型'): deepseek.test_connection()
    def test_payload_and_bearer(self):
        deepseek.save_settings({'key':'test-only-key'})
        class Response:
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def read(self): return b'{"ok":true}'
        with patch('urllib.request.OpenerDirector.open',return_value=Response()) as mock:
            deepseek.request('/chat/completions',{'model':'deepseek-flash'})
            req=mock.call_args.args[0]
            self.assertEqual(req.full_url,'https://api.deepseek.com/chat/completions')
            self.assertEqual(req.get_header('Authorization'),'Bearer test-only-key')
            self.assertEqual(json.loads(req.data)['model'],'deepseek-flash')

if __name__=='__main__': unittest.main()
