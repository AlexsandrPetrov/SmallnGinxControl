"""Удалённый скрипт: сайты из каталогов include dir/* (как /etc/nginx/vhosts/* на RED OS)."""
import tempfile
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from .remote_worker import RemoteWorker

SITE = 'server {\n    listen 80;\n    server_name static.example.test;\n    root /var/www/static;\n}\n'


class RemoteFlatSiteTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = self.root = Path(self.temporary.name).resolve()
        for name in ('conf.d', 'vhosts', 'logs'):
            (root / name).mkdir()
        (root / 'nginx.conf').write_text(f'http {{\n    include {root}/vhosts/*;\n    include {root}/conf.d/*.conf;\n}}\n')
        (root / 'vhosts' / 'static.conf').write_text(SITE)
        self.worker = RemoteWorker(root, root / 'logs', root / 'state')
        nginx_t = f'# configuration file {root}/nginx.conf:\n# configuration file {root}/vhosts/static.conf:\n'
        response = type('Result', (), {'returncode': 0, 'stdout': nginx_t, 'stderr': ''})()
        for target, kwargs in ((self.worker, {'attribute': 'command', 'return_value': response}),
                               (self.worker, {'attribute': 'lock', 'return_value': nullcontext()}),
                               (self.worker, {'attribute': 'validate', 'return_value': 'ok'}),
                               (self.worker, {'attribute': 'reload'})):
            patcher = patch.object(target, kwargs.pop('attribute'), **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def config(self, identifier):
        return next(item for item in self.worker.inventory()['configs'] if item['id'] == identifier)

    def test_flat_directory_detected_from_nginx_conf(self):
        self.assertEqual(self.worker.flat_dirs(), [self.root / 'vhosts'])
        self.assertTrue(self.config('vhosts/static.conf')['toggleable'])

    def test_disable_moves_out_and_enable_moves_back(self):
        item = self.config('vhosts/static.conf')
        self.worker.edit('toggle', {'id': item['id'], 'revision': item['revision'], 'enabled': False})
        self.assertTrue((self.root / 'vhosts.disabled' / 'static.conf').is_file())
        self.assertFalse((self.root / 'vhosts' / 'static.conf').exists())
        disabled = self.config('vhosts.disabled/static.conf')
        self.assertTrue(disabled['toggleable'])
        self.worker.edit('toggle', {'id': disabled['id'], 'revision': disabled['revision'], 'enabled': True})
        self.assertEqual((self.root / 'vhosts' / 'static.conf').read_text(), SITE)

    def test_delete_allowed_for_flat_site(self):
        item = self.config('vhosts/static.conf')
        self.worker.edit('delete', {'id': item['id'], 'revision': item['revision']})
        self.assertFalse((self.root / 'vhosts' / 'static.conf').exists())
