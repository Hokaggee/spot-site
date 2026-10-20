import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from server import make_server


class HttpTests(unittest.TestCase):
    def test_only_the_homepage_demo_can_be_framed_on_the_same_origin(self):
        for path, policy, ancestor in [('/', 'DENY', "'none'"), ('/?preview=loader', 'SAMEORIGIN', "'self'"),
                                       ('/admin?preview=loader', 'DENY', "'none'")]:
            connection = HTTPConnection('127.0.0.1', self.port)
            connection.request('GET', path)
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.getheader('X-Frame-Options'), policy)
            self.assertIn('frame-ancestors '+ancestor, response.getheader('Content-Security-Policy'))
            connection.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server('127.0.0.1', 0, Path(self.tmp.name), refresh=False)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, method, path, data=None, origin=True, csrf=True):
        connection = HTTPConnection('127.0.0.1', self.port)
        headers = {'Content-Type': 'application/json', 'Cookie': self.cookie}
        if origin:
            headers['Origin'] = f'http://127.0.0.1:{self.port}'
        if csrf:
            headers['X-CSRF-Token'] = self.csrf
        connection.request(method, path, json.dumps(data).encode() if data is not None else None, headers)
        response = connection.getresponse()
        body = response.read()
        cookie = response.getheader('Set-Cookie')
        if cookie:
            self.cookie = cookie.split(';')[0]
        status = response.status
        connection.close()
        try:
            return status, json.loads(body)
        except ValueError:
            return status, body

    def test_login_csrf_and_logout(self):
        self.assertEqual(self.request('POST', '/api/admin/albums', {'title': 'Туса', 'date': '2026-10-16'})[0], 401)
        self.server.store.set_password('a-long-spot-password', username='spot-editor')
        self.assertEqual(self.request('POST', '/api/admin/login', {'username': 'wrong', 'password': 'a-long-spot-password'})[0], 401)
        status, data = self.request('POST', '/api/admin/login', {'username': 'spot-editor', 'password': 'a-long-spot-password'})
        self.assertEqual(status, 200)
        self.csrf = data['csrf']
        self.assertEqual(self.request('POST', '/api/admin/setup', {'password': 'another-password'})[0], 404)
        self.assertEqual(self.request('POST', '/api/admin/albums', {'title': 'Туса', 'date': '2026-10-16'}, csrf=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/admin/albums', {'title': 'Туса', 'date': '2026-10-16'}, origin=False)[0], 403)
        status, album = self.request('POST', '/api/admin/albums', {'title': 'Туса', 'date': '2026-10-16'})
        self.assertEqual(status, 201)
        self.assertEqual(self.request('GET', '/api/albums')[1]['albums'], [])
        self.assertEqual(self.request('GET', '/api/albums/'+album['id'])[0], 404)
        self.assertEqual(self.request('POST', '/api/admin/logout', {})[0], 200)
        self.assertEqual(self.request('GET', '/api/admin/albums')[0], 401)

    def test_private_files_and_path_traversal_are_blocked(self):
        self.server.store.set_password('file-private-password')
        for path in ['/server.py', '/store.py', '/auth.py', '/manage_admin.py', '/.spot-data/spot.sqlite3', '/.spot-data/admin-auth.json', '/admin-auth.json', '/assets/../server.py', '/assets/%2e%2e/server.py', '/assets/%2e%2e/.spot-data/admin-auth.json', '/tests/test_http.py']:
            self.assertEqual(self.request('GET', path)[0], 404, path)
        self.assertEqual(self.request('GET', '/')[0], 200)
        self.assertEqual(self.request('GET', '/admin')[0], 200)

    def test_browser_cannot_claim_an_unconfigured_admin(self):
        self.assertEqual(self.request('POST', '/api/admin/setup', {'password':'attacker-password'})[0], 404)
        self.assertFalse(self.server.store.configured())


if __name__ == '__main__':
    unittest.main()
