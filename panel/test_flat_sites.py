"""Каталоги вида include /etc/nginx/vhosts/*; (RED OS, CentOS, панели хостинга)."""
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from .nginx import NginxManager
from .transactions import OperationError

STATIC_SITE = 'server {\n    listen 80;\n    server_name static.example.test;\n    root /var/www/static;\n}\n'
PROXY_SITE = 'server {\n    listen 80;\n    server_name app.example.test;\n    location / {\n        proxy_pass http://127.0.0.1:8010;\n    }\n}\n'


class FlatSiteDirTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = self.root = Path(self.temporary.name)
        for name in ('conf.d', 'vhosts', 'logs', 'maintenance'):
            (root / name).mkdir()
        (root / 'maintenance' / 'maitenance.html').write_text('maintenance')
        (root / 'nginx.conf').write_text('events {}\nhttp {\n    include vhosts/*;\n    include conf.d/*.conf;\n}\n')
        (root / 'vhosts' / 'static.conf').write_text(STATIC_SITE)
        (root / 'vhosts' / 'app.conf').write_text(PROXY_SITE)
        self.override = override_settings(NGINX_ROOT=root, NGINX_LOG_ROOT=root / 'logs', STATE_DIR=root, SNC_MODE='demo',
                                          SNC_FLAT_SITE_DIRS=('vhosts',), SNC_NEW_SITE_DIR='vhosts')
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.manager = NginxManager(maintenance_root=root / 'maintenance')

    def items(self):
        return {item['id']: item for item in self.manager.inventory()['items']}

    def test_flat_sites_are_listed_and_toggleable(self):
        items = self.items()
        self.assertTrue(items['vhosts/static.conf']['toggleable'])
        self.assertTrue(items['vhosts/static.conf']['enabled'])

    def test_disable_moves_file_out_of_included_directory_and_back(self):
        item = self.items()['vhosts/static.conf']
        self.manager.toggle(item['id'], False, item['revision'])
        self.assertFalse((self.root / 'vhosts' / 'static.conf').exists())
        self.assertEqual((self.root / 'vhosts.disabled' / 'static.conf').read_text(), STATIC_SITE)
        disabled = self.items()['vhosts.disabled/static.conf']
        self.assertFalse(disabled['enabled'])
        self.manager.toggle(disabled['id'], True, disabled['revision'])
        self.assertEqual((self.root / 'vhosts' / 'static.conf').read_text(), STATIC_SITE)
        self.assertFalse((self.root / 'vhosts.disabled' / 'static.conf').exists())

    def test_disabling_proxy_uses_maintenance_page_in_place(self):
        item = self.items()['vhosts/app.conf']
        self.manager.toggle(item['id'], False, item['revision'])
        self.assertIn('return 503;', (self.root / 'vhosts' / 'app.conf').read_text())
        item = self.items()['vhosts/app.conf']
        self.manager.toggle(item['id'], True, item['revision'])
        self.assertEqual((self.root / 'vhosts' / 'app.conf').read_text(), PROXY_SITE)

    def test_delete_keeps_backup(self):
        item = self.items()['vhosts/static.conf']
        self.manager.delete(item['id'], item['revision'])
        self.assertFalse((self.root / 'vhosts' / 'static.conf').exists())
        self.assertTrue(any(p.name.endswith('static.conf.bak') for p in (self.root / 'backups').iterdir()))

    def test_new_sites_are_created_in_flat_directory(self):
        self.manager.create({'name': 'new.example.test', 'kind': 'host', 'target': '/var/www/new', 'port': 80})
        self.assertTrue((self.root / 'vhosts' / 'new.example.test.conf').is_file())
        self.assertFalse(any((self.root / 'conf.d').iterdir()))

    def test_name_taken_in_disabled_directory_is_rejected(self):
        (self.root / 'vhosts.disabled').mkdir()
        (self.root / 'vhosts.disabled' / 'old.example.test.conf').write_text(STATIC_SITE.replace('static', 'old'))
        with self.assertRaisesRegex(OperationError, 'уже существует|уже присутствует'):
            self.manager.create({'name': 'old.example.test', 'kind': 'host', 'target': '/var/www/old', 'port': 80})

    def test_unmanaged_directories_stay_read_only(self):
        with override_settings(SNC_FLAT_SITE_DIRS=()):
            manager = NginxManager(maintenance_root=self.root / 'maintenance')
            self.assertNotIn('vhosts/static.conf', {item['id'] for item in manager.inventory()['items']})
