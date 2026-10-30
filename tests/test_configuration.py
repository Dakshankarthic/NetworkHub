import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from network_engine import Engine, PRIVATE_ROUTES
from network_routes import Network


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.engine = object.__new__(Engine)
        self.engine.secret = 'unit-test-secret'
        self.adapters = [Network('Wired',19,'192.0.2.2'), Network('Phone',49,'198.51.100.2')]

    def test_routes_use_only_selected_adapters(self):
        with patch('network_engine.discover_networks',return_value=self.adapters):
            config = self.engine.configuration(['Phone'])
        self.assertEqual([p['interface-name'] for p in config['proxies']],['Phone'])
        self.assertEqual(config['proxy-groups'][0]['strategy'],'round-robin')
        self.assertEqual(config['proxy-groups'][0]['proxies'],['Link · Phone'])
        self.assertFalse(config['tun']['enable'])

    def test_tun_private_routes_and_loopback_controller(self):
        with patch('network_engine.discover_networks',return_value=self.adapters):
            config = self.engine.configuration(['Wired','Phone'],tun=True)
        self.assertTrue(config['tun']['enable'])
        self.assertEqual(config['tun']['route-exclude-address'],PRIVATE_ROUTES)
        self.assertEqual(config['external-controller'],'127.0.0.1:19090')
        self.assertEqual(config['bind-address'],'127.0.0.1')
        self.assertFalse(config['allow-lan'])
        self.assertEqual(config['secret'],self.engine.secret)

    def test_disconnected_selection_has_clear_error(self):
        with patch('network_engine.discover_networks',return_value=self.adapters):
            with self.assertRaisesRegex(RuntimeError,'Connect at least one'):
                self.engine.configuration(['Disconnected'])
