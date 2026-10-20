"""Durable albums, private originals and local editor authentication."""
import hashlib
import io
import json
import secrets
import shutil
import sqlite3
import tempfile
import time
import warnings
import zipfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from auth import CredentialFile

MAX_UPLOAD = 40 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000


class ValidationError(ValueError):
    pass


class Store:
    def __init__(self, root, auth_file=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.photos_dir = self.root / 'photos'
        self.photos_dir.mkdir(exist_ok=True)
        self.db_path = self.root / 'spot.sqlite3'
        self.credentials = CredentialFile(auth_file or self.root / 'admin-auth.json')
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS albums(
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT NOT NULL,
                    cover_id TEXT, published INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS photos(
                    id TEXT PRIMARY KEY, album_id TEXT NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL, ext TEXT NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS photos_album ON photos(album_id);
            ''')
            if 'auth_version' not in {row['name'] for row in db.execute('PRAGMA table_info(sessions)')}:
                db.execute('ALTER TABLE sessions ADD COLUMN auth_version TEXT')
            legacy = db.execute("SELECT value FROM settings WHERE key='password'").fetchone()
            if legacy and not self.credentials.path.exists():
                salt, digest = json.loads(legacy['value'])
                self.credentials.write({'version': 1, 'username': 'admin', 'algorithm': 'pbkdf2_sha256',
                    'iterations': 310_000, 'salt': salt, 'password_hash': digest})
            if legacy and self.credentials.read():
                db.execute('PRAGMA secure_delete=ON')
                db.execute("DELETE FROM settings WHERE key='password'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def fields(title, event_date):
        title = str(title).strip()
        if not title or len(title) > 120:
            raise ValidationError('Укажите название вечеринки: от 1 до 120 символов.')
        try:
            event_date = date.fromisoformat(str(event_date)).isoformat()
        except ValueError:
            raise ValidationError('Выберите дату вечеринки.') from None
        return title, event_date

    def create_album(self, title, event_date):
        title, event_date = self.fields(title, event_date)
        album_id = secrets.token_hex(12)
        with self.connect() as db:
            db.execute('INSERT INTO albums VALUES(?,?,?,NULL,0,?)', (album_id, title, event_date, time.time()))
        return self.get_album(album_id, admin=True)

    @staticmethod
    def album_dict(row):
        data = dict(row)
        data['published'] = bool(data['published'])
        data['cover_url'] = f"/media/{data['cover_id']}/thumb" if data['cover_id'] else None
        return data

    @staticmethod
    def photo_dict(row):
        result = dict(row)
        key = result['id']
        result.update(thumb_url=f'/media/{key}/thumb', url=f'/media/{key}/preview', download_url=f'/media/{key}/original?download=1')
        return result

    def list_albums(self, admin=False):
        with self.connect() as db:
            rows = db.execute('''SELECT a.*, COUNT(p.id) photo_count FROM albums a
                LEFT JOIN photos p ON p.album_id=a.id
                WHERE (? OR a.published=1) GROUP BY a.id ORDER BY a.date DESC,a.created DESC''', (bool(admin),)).fetchall()
        return [self.album_dict(r) for r in rows]

    def get_album(self, album_id, admin=False):
        with self.connect() as db:
            row = db.execute('SELECT * FROM albums WHERE id=? AND (? OR published=1)', (album_id, bool(admin))).fetchone()
            if not row:
                return None
            photos = db.execute('SELECT * FROM photos WHERE album_id=? ORDER BY created,id', (album_id,)).fetchall()
        result = self.album_dict(row)
        result.update(photos=[self.photo_dict(p) for p in photos], photo_count=len(photos))
        return result

    def update_album(self, album_id, changes):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM albums WHERE id=?', (album_id,)).fetchone()
            if not row:
                raise ValidationError('Альбом не найден.')
            title, event_date = self.fields(changes.get('title', row['title']), changes.get('date', row['date']))
            cover = changes.get('cover_id', row['cover_id'])
            published = changes.get('published', bool(row['published']))
            if not isinstance(published, bool):
                raise ValidationError('Неверное состояние публикации.')
            photo = db.execute('SELECT id FROM photos WHERE id=? AND album_id=?', (cover, album_id)).fetchone()
            if cover and not photo:
                raise ValidationError('Выберите обложку из фотографий этого альбома.')
            if published and not photo:
                raise ValidationError('Загрузите фотографии и выберите обложку перед публикацией.')
            db.execute('UPDATE albums SET title=?,date=?,cover_id=?,published=? WHERE id=?', (title, event_date, cover, published, album_id))
        return self.get_album(album_id, admin=True)

    def add_photo(self, album_id, content, filename):
        if not content or len(content) > MAX_UPLOAD:
            raise ValidationError('Размер фотографии должен быть не более 40 МБ.')
        if not self.get_album(album_id, admin=True):
            raise ValidationError('Альбом не найден.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as source:
                    ext = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(source.format)
                    if not ext or source.width * source.height > 40_000_000:
                        raise ValidationError('Поддерживаются JPEG, PNG и WebP до 40 мегапикселей.')
                    source.verify()
                with Image.open(io.BytesIO(content)) as source:
                    source.load()
                    image = ImageOps.exif_transpose(source).convert('RGB')
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning, ValueError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError('Файл повреждён или не является фотографией JPEG, PNG или WebP.') from None
        photo_id = secrets.token_hex(16)
        folder = self.photos_dir / photo_id
        folder.mkdir()
        filename = str(filename).replace('\\', '/').rsplit('/', 1)[-1]
        filename = ''.join(c for c in filename if c.isprintable()).strip()[:180] or f'photo.{ext}'
        try:
            (folder / f'original.{ext}').write_bytes(content)
            for variant, size, quality in [('preview', 2000, 88), ('thumb', 640, 82)]:
                copy = image.copy()
                copy.thumbnail((size, size), Image.Resampling.LANCZOS)
                copy.save(folder / f'{variant}.jpg', 'JPEG', quality=quality, optimize=True)
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT INTO photos VALUES(?,?,?,?,?)', (photo_id, album_id, filename, ext, time.time()))
                db.execute('UPDATE albums SET cover_id=? WHERE id=? AND cover_id IS NULL', (photo_id, album_id))
                row = db.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
            return self.photo_dict(row)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        finally:
            image.close()

    def delete_photo(self, album_id, photo_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT id FROM photos WHERE id=? AND album_id=?', (photo_id, album_id)).fetchone()
            if not row:
                raise ValidationError('Фотография не найдена.')
            db.execute('DELETE FROM photos WHERE id=?', (photo_id,))
            next_photo = db.execute('SELECT id FROM photos WHERE album_id=? ORDER BY created,id LIMIT 1', (album_id,)).fetchone()
            db.execute('UPDATE albums SET cover_id=? WHERE id=? AND cover_id=?', (next_photo['id'] if next_photo else None, album_id, photo_id))
            if not next_photo:
                db.execute('UPDATE albums SET published=0 WHERE id=?', (album_id,))
        shutil.rmtree(self.photos_dir / photo_id, ignore_errors=True)

    def media(self, photo_id, variant, admin=False):
        if variant not in ('original', 'preview', 'thumb'):
            return None
        with self.connect() as db:
            row = db.execute('''SELECT p.* FROM photos p JOIN albums a ON p.album_id=a.id
                WHERE p.id=? AND (? OR a.published=1)''', (photo_id, bool(admin))).fetchone()
        if not row:
            return None
        extension = row['ext'] if variant == 'original' else 'jpg'
        path = self.photos_dir / row['id'] / f'{variant}.{extension}'
        if not path.is_file():
            return None
        return {'path': path, 'filename': row['filename'], 'type': {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}[extension]}

    def album_zip(self, album_id, admin=False):
        album = self.get_album(album_id, admin=admin)
        if not album:
            raise ValidationError('Альбом не найден.')
        archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        try:
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as output:
                for index, photo in enumerate(album['photos'], 1):
                    media = self.media(photo['id'], 'original', admin=admin)
                    if media:
                        output.write(media['path'], arcname=f"{index:03d}_{Path(photo['filename']).stem}.{photo['ext']}")
            archive.seek(0)
            return archive
        except Exception:
            archive.close()
            raise

    def configured(self):
        return self.credentials.read() is not None

    def set_password(self, password, username='admin', replace=False):
        try:
            self.credentials.create(username, password, replace=replace)
        except ValueError as error:
            raise ValidationError(str(error)) from None

    def check_password(self, password, username='admin'):
        return self.credentials.verify(username, password)

    def authenticate(self, password, username='admin'):
        return self.credentials.authenticate(username, password)

    def create_session(self, auth_version=None):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions(token,csrf,expires,auth_version) VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), csrf, time.time() + 12*3600, auth_version if auth_version is not None else self.credentials.fingerprint()))
        return {'token': token, 'csrf': csrf}

    def session(self, token):
        if not token:
            return None
        with self.connect() as db:
            row = db.execute('SELECT csrf FROM sessions WHERE token=? AND expires>? AND auth_version=?', (hashlib.sha256(token.encode()).hexdigest(), time.time(), self.credentials.fingerprint())).fetchone()
        return dict(row) if row else None

    def delete_session(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))
