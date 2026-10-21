"""SPOT local/app server. Run: python3 server.py --port 8081."""
import argparse
import hmac
import json
import logging
import mimetypes
import os
import re
import shutil
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from events import Calendar
from store import MAX_UPLOAD, Store, ValidationError

ROOT = Path(__file__).resolve().parent
PUBLIC_FILES = {'index.html', 'styles.css', 'fonts.css', 'app.js', 'admin.html', 'admin.css', 'admin.js', 'legal.html', 'legal.css'}


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Handler(BaseHTTPRequestHandler):
    server_version = 'SPOT/1.0'

    def log_message(self, fmt, *args):
        if args and str(args[1] if len(args) > 1 else '') not in ('200', '206', '201'):
            logging.info(fmt, *args)

    def end_headers(self):
        location = urlsplit(self.path)
        loader_demo = location.path == '/' and parse_qs(location.query).get('preview') == ['loader']
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options', 'SAMEORIGIN' if loader_demo else 'DENY')
        self.send_header('Cache-Control', 'no-store')
        ancestors = "'self'" if loader_demo else "'none'"
        self.send_header('Content-Security-Policy', f"default-src 'self'; img-src 'self' blob: data: https://cdn.qtickets.tech https://avatars.mds.yandex.net https://avatars.mds.yandex.ru; media-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; font-src 'self'; frame-ancestors {ancestors}; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def json(self, status, payload, cookie=None):
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def read_body(self, limit=65536):
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError(400, 'Неверный размер запроса.')
        if length < 0 or length > limit:
            raise APIError(413, 'Файл слишком большой. Максимум — 40 МБ на фотографию.')
        self.connection.settimeout(45)
        data = self.rfile.read(length)
        if len(data) != length:
            raise APIError(400, 'Загрузка прервалась. Повторите её.')
        return data

    def body_json(self):
        try:
            payload = json.loads(self.read_body())
            if not isinstance(payload, dict):
                raise ValueError()
            return payload
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, 'Неверный формат запроса.') from None

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:
            return ''
        return cookie['spot_session'].value if 'spot_session' in cookie else ''

    def authenticated(self, write=False):
        session = self.server.store.session(self.token())
        if not session:
            raise APIError(401, 'Войдите снова. Уже загруженные фотографии сохранены в черновике.')
        if write and not hmac.compare_digest(session['csrf'], self.headers.get('X-CSRF-Token', '')):
            raise APIError(403, 'Обновите страницу и повторите действие.')
        return session

    def check_origin(self):
        expected = self.server.origin or f"http://{self.headers.get('Host', '')}"
        if self.headers.get('Origin') != expected:
            raise APIError(403, 'Запрос разрешён только со страницы этого сайта.')

    def cookie(self, token='', max_age=43200):
        secure = '; Secure' if self.server.origin.startswith('https://') else ''
        return f'spot_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}{secure}'

    def file(self, path, content_type=None, filename=None):
        size = path.stat().st_size
        start, end, partial = 0, size-1, False
        requested = self.headers.get('Range', '')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match or not any(match.groups()):
                raise APIError(416, 'Неверный диапазон файла.')
            if match.group(1):
                start = int(match.group(1))
                end = min(end, int(match.group(2))) if match.group(2) else end
            else:
                start = max(0, size-int(match.group(2)))
            if start > end or start >= size:
                raise APIError(416, 'Диапазон за пределами файла.')
            partial = True
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', content_type or mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Accept-Ranges', 'bytes')
        if partial:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if filename:
            self.send_header('Content-Disposition', f"attachment; filename=photo{path.suffix}; filename*=UTF-8''{quote(filename, safe='')}")
        self.end_headers()
        if self.command != 'HEAD':
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def dispatch(self):
        path = unquote(urlsplit(self.path).path)
        method = 'GET' if self.command == 'HEAD' else self.command
        store = self.server.store
        if self.server.origin:
            expected_host = urlsplit(self.server.origin).netloc
            if self.headers.get('Host') != expected_host:
                raise APIError(400, 'Неверный адрес сайта.')
        elif self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            raise APIError(400, 'Настройте SPOT_ORIGIN для доступа по этому адресу.')
        if method in ('POST', 'PATCH', 'DELETE'):
            self.check_origin()
        if path == '/api/events' and method == 'GET':
            return self.json(200, self.server.calendar.payload())
        if path == '/api/admin/session' and method == 'GET':
            session = store.session(self.token())
            return self.json(200, {'authenticated': bool(session), 'configured': store.configured(),
                'csrf': session['csrf'] if session else None})
        if path == '/api/admin/setup':
            raise APIError(404, 'Страница не найдена.')
        if path == '/api/admin/login' and method == 'POST':
            key = self.client_address[0]
            with self.server.attempt_lock:
                history = [t for t in self.server.attempts.get(key, []) if t > time.time()-600]
                if len(history) >= 10:
                    raise APIError(429, 'Слишком много попыток. Попробуйте через 10 минут.')
                history.append(time.time())
                self.server.attempts[key] = history
            data = self.body_json()
            verified_version = store.authenticate(data.get('password', ''), username=data.get('username', ''))
            if not verified_version:
                raise APIError(401, 'Неверный логин или пароль.')
            session = store.create_session(auth_version=verified_version)
            return self.json(200, {'csrf': session['csrf']}, self.cookie(session['token']))
        if path.startswith('/api/admin/'):
            self.authenticated(write=method != 'GET')
        if path == '/api/admin/logout' and method == 'POST':
            store.delete_session(self.token())
            return self.json(200, {'ok': True}, self.cookie(max_age=0))
        if path in ('/api/albums', '/api/admin/albums'):
            if method == 'GET':
                return self.json(200, {'albums': store.list_albums(admin='/admin/' in path)})
            if method == 'POST' and '/admin/' in path:
                data = self.body_json()
                return self.json(201, store.create_album(data.get('title', ''), data.get('date', '')))
        album_match = re.fullmatch(r'/api/(admin/)?albums/([a-f0-9]{24})(/photos|/archive)?(?:/([a-f0-9]{32}))?', path)
        if album_match:
            admin, album_id, action, photo_id = album_match.groups()
            if method == 'GET' and not action:
                album = store.get_album(album_id, admin=bool(admin))
                if not album:
                    raise APIError(404, 'Альбом не найден.')
                return self.json(200, album)
            if method == 'PATCH' and admin and not action:
                return self.json(200, store.update_album(album_id, self.body_json()))
            if method == 'POST' and admin and action == '/photos' and not photo_id:
                content = self.read_body(MAX_UPLOAD)
                filename = unquote(self.headers.get('X-Filename', 'photo.jpg'))
                return self.json(201, store.add_photo(album_id, content, filename))
            if method == 'DELETE' and admin and action == '/photos' and photo_id:
                store.delete_photo(album_id, photo_id)
                return self.json(200, {'ok': True})
            if method == 'GET' and action == '/archive' and not photo_id:
                if not store.get_album(album_id, admin=bool(admin)):
                    raise APIError(404, 'Альбом не найден.')
                with self.server.zip_lock:
                    with store.album_zip(album_id, admin=bool(admin)) as archive:
                        archive.seek(0, 2)
                        size = archive.tell()
                        archive.seek(0)
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/zip')
                        self.send_header('Content-Length', str(size))
                        self.send_header('Content-Disposition', f'attachment; filename=SPOT-{album_id}.zip')
                        self.end_headers()
                        if self.command != 'HEAD':
                            shutil.copyfileobj(archive, self.wfile, length=65536)
                return
        media_match = re.fullmatch(r'/media/([a-f0-9]{32})/(thumb|preview|original)', path)
        if media_match and method == 'GET':
            photo_id, variant = media_match.groups()
            media = store.media(photo_id, variant, admin=bool(store.session(self.token())))
            if not media:
                raise APIError(404, 'Фотография недоступна.')
            return self.file(media['path'], media['type'], media['filename'] if variant == 'original' else None)
        if method == 'GET':
            relative = {'/': 'index.html', '/admin': 'admin.html', '/admin/': 'admin.html'}.get(path, path.lstrip('/'))
            file = (ROOT / relative).resolve()
            asset_root = (ROOT / 'assets').resolve()
            allowed = relative in PUBLIC_FILES or (path.startswith('/assets/') and file.is_relative_to(asset_root))
            if file == store.credentials.path.resolve():
                allowed = False
            if allowed and file.is_file() and not any(part.startswith('.') for part in Path(relative).parts):
                return self.file(file)
        raise APIError(404, 'Страница не найдена.')

    def handle_request(self):
        try:
            self.dispatch()
        except APIError as error:
            self.json(error.status, {'error': error.message})
        except ValidationError as error:
            self.json(400, {'error': str(error)})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            logging.exception('Request failed')
            self.json(500, {'error': 'Не удалось выполнить действие. Попробуйте ещё раз.'})

    do_GET = do_HEAD = do_POST = do_PATCH = do_DELETE = handle_request


def make_server(host, port, data_dir, refresh=True, origin='', auth_file=None):
    store = Store(data_dir, auth_file=auth_file)
    server = ThreadingHTTPServer((host, port), Handler)
    server.store, server.calendar, server.origin = store, Calendar(store.root), origin.rstrip('/')
    server.attempts, server.attempt_lock, server.zip_lock = {}, threading.Lock(), threading.Semaphore(2)
    if refresh:
        server.calendar.start()
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--data-dir', type=Path, default=ROOT / '.spot-data')
    parser.add_argument('--auth-file', type=Path, default=os.environ.get('SPOT_AUTH_FILE'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    server = make_server(args.host, args.port, args.data_dir, origin=os.environ.get('SPOT_ORIGIN', ''), auth_file=args.auth_file)
    if not server.store.configured() and os.environ.get('SPOT_ADMIN_PASSWORD'):
        server.store.set_password(os.environ['SPOT_ADMIN_PASSWORD'], username=os.environ.get('SPOT_ADMIN_USERNAME', 'admin'))
    if not server.store.configured():
        parser.error('Сначала создайте файл доступа командой python3 manage_admin.py. Можно указать SPOT_AUTH_FILE.')
    print(f'SPOT: http://{args.host}:{args.port}/\nSMM editor: http://{args.host}:{args.port}/admin', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
