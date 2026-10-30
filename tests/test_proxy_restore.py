from pathlib import Path
import sys
import tempfile
import unittest
import uuid
import winreg

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from network_engine import WindowsProxy


class ProxyRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        key_path = 'Software\\NetworkHubTest_'+uuid.uuid4().hex

        class IsolatedProxy(WindowsProxy):
            path = key_path
            backup_path = Path(self.temp.name)/'backup.json'
            def notify(self):
                pass

        self.proxy = IsolatedProxy()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,key_path) as key:
            winreg.SetValueEx(key,'ProxyEnable',0,winreg.REG_DWORD,0)
            winreg.SetValueEx(key,'ProxyServer',0,winreg.REG_SZ,'original.example:123')
            winreg.SetValueEx(key,'AutoConfigURL',0,winreg.REG_SZ,'https://example.invalid/proxy.pac')

    def tearDown(self):
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,self.proxy.path)
        self.temp.cleanup()

    def test_previous_proxy_and_pac_are_restored(self):
        original = self.proxy.current()
        self.proxy.enable()
        self.assertTrue(self.proxy.enabled())
        self.assertIsNone(self.proxy.current()['AutoConfigURL'])
        self.proxy.restore()
        self.assertEqual(self.proxy.current(),original)
        self.assertFalse(self.proxy.backup_path.exists())

    def test_independent_proxy_changes_are_preserved(self):
        self.proxy.enable()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,self.proxy.path,0,winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key,'ProxyServer',0,winreg.REG_SZ,'new.example:456')
        modified = self.proxy.current()
        self.proxy.restore()
        self.assertEqual(self.proxy.current(),modified)
