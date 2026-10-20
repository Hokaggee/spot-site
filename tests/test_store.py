import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image

from store import Store, ValidationError


def jpeg(color='red'):
    out = io.BytesIO()
    Image.new('RGB', (80, 60), color).save(out, 'JPEG')
    return out.getvalue()


class AlbumTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_publish_requires_photo_and_valid_cover(self):
        album = self.store.create_album('Пятница на СПОТе', '2026-10-16')
        with self.assertRaises(ValidationError):
            self.store.update_album(album['id'], {'published': True})
        photo = self.store.add_photo(album['id'], jpeg(), 'фото.jpg')
        with self.assertRaises(ValidationError):
            self.store.update_album(album['id'], {'cover_id': 'not-a-photo', 'published': True})
        self.store.update_album(album['id'], {'cover_id': photo['id'], 'published': True})
        visible = self.store.list_albums()
        self.assertEqual(visible[0]['title'], 'Пятница на СПОТе')
        self.assertEqual(visible[0]['photo_count'], 1)
        self.assertEqual(self.store.get_album(album['id'])['photos'][0]['id'], photo['id'])

    def test_drafts_and_originals_are_private_until_publication(self):
        album = self.store.create_album('Черновик', '2026-10-16')
        photo = self.store.add_photo(album['id'], jpeg(), '../../фото.jpg')
        self.assertEqual(self.store.list_albums(), [])
        self.assertIsNone(self.store.get_album(album['id']))
        self.assertIsNone(self.store.media(photo['id'], 'original'))
        self.assertTrue(self.store.media(photo['id'], 'original', admin=True)['path'].is_file())
        self.store.update_album(album['id'], {'published': True})
        self.assertEqual(self.store.media(photo['id'], 'original')['path'].read_bytes(), jpeg())
        self.store.update_album(album['id'], {'published': False})
        self.assertIsNone(self.store.media(photo['id'], 'thumb'))

    def test_persistence_delete_cover_and_zip(self):
        album = self.store.create_album('Архив', '2026-10-15')
        first = self.store.add_photo(album['id'], jpeg(), 'IMG.jpg')
        second = self.store.add_photo(album['id'], jpeg('blue'), 'IMG.jpg')
        self.store.update_album(album['id'], {'cover_id': first['id'], 'published': True})
        other = Store(Path(self.tmp.name))
        self.assertEqual(other.list_albums()[0]['photo_count'], 2)
        with other.album_zip(album['id']) as archive:
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(len(set(z.namelist())), 2)
                self.assertEqual(z.read(z.namelist()[0]), jpeg())
        other.delete_photo(album['id'], first['id'])
        self.assertEqual(other.get_album(album['id'])['cover_id'], second['id'])
        other.delete_photo(album['id'], second['id'])
        self.assertEqual(other.list_albums(), [])

    def test_bad_images_and_metadata_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.store.create_album('  ', '2026-10-16')
        with self.assertRaises(ValidationError):
            self.store.create_album('Название', 'garbage')
        album = self.store.create_album('Туса', '2026-10-16')
        for data in [b'<svg onload="alert(1)"></svg>', b'not an image', jpeg()[:30]]:
            with self.assertRaises(ValidationError):
                self.store.add_photo(album['id'], data, 'image.jpg')
        self.assertEqual(self.store.get_album(album['id'], admin=True)['photo_count'], 0)

    def test_album_accepts_photos_beyond_five_hundred(self):
        album = self.store.create_album('Большая вечеринка', '2026-10-16')
        with self.store.connect() as db:
            db.executemany('INSERT INTO photos VALUES(?,?,?,?,?)',
                [(f'{index:032x}', album['id'], f'{index}.jpg', 'jpg', index)
                 for index in range(500)])
        photo = self.store.add_photo(album['id'], jpeg(), 'ещё-фото.jpg')
        saved = self.store.get_album(album['id'], admin=True)
        self.assertEqual(saved['photo_count'], 501)
        self.assertEqual(saved['photos'][-1]['id'], photo['id'])

    def test_password_is_hashed_and_sessions_expire(self):
        self.assertFalse(self.store.configured())
        self.store.set_password('correct-horse-spot')
        self.assertFalse(self.store.check_password('wrong'))
        self.assertTrue(self.store.check_password('correct-horse-spot'))
        self.assertNotIn('correct-horse-spot', self.store.db_path.read_bytes().decode('latin1'))
        session = self.store.create_session()
        self.assertEqual(self.store.session(session['token'])['csrf'], session['csrf'])
        self.store.delete_session(session['token'])
        self.assertIsNone(self.store.session(session['token']))

    def test_credentials_live_in_a_private_file_and_require_correct_login(self):
        self.store.set_password('separate-file-password', username='spot-editor')
        path = Path(self.tmp.name) / 'admin-auth.json'
        self.assertTrue(path.is_file())
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertNotIn('separate-file-password', path.read_text())
        self.assertEqual(json.loads(path.read_text())['username'], 'spot-editor')
        self.assertFalse(self.store.check_password('separate-file-password', username='wrong'))
        self.assertTrue(Store(Path(self.tmp.name)).check_password('separate-file-password', username='spot-editor'))
        with self.store.connect() as db:
            self.assertIsNone(db.execute("SELECT value FROM settings WHERE key='password'").fetchone())

    def test_credential_rotation_invalidates_sessions(self):
        self.store.set_password('old-secret-password')
        session = self.store.create_session()
        self.store.set_password('new-secret-password', replace=True)
        self.assertIsNone(self.store.session(session['token']))
        self.assertFalse(self.store.check_password('old-secret-password'))
        self.assertTrue(self.store.check_password('new-secret-password'))

    def test_password_rotation_cannot_renew_an_inflight_old_login(self):
        self.store.set_password('old-secret-password')
        verified_version = self.store.authenticate('old-secret-password', username='admin')
        self.assertTrue(verified_version)
        self.store.set_password('new-secret-password', replace=True)
        session = self.store.create_session(auth_version=verified_version)
        self.assertIsNone(self.store.session(session['token']))

    def test_existing_password_migrates_without_resetting_it(self):
        import hashlib
        salt = 'test-migration-salt'
        digest = hashlib.pbkdf2_hmac('sha256', b'existing-spot-password', salt.encode(), 310000).hex()
        with self.store.connect() as db:
            db.execute("INSERT INTO settings VALUES('password',?)", (json.dumps([salt, digest]),))
        migrated = Store(Path(self.tmp.name))
        self.assertTrue((Path(self.tmp.name) / 'admin-auth.json').exists())
        self.assertTrue(migrated.check_password('existing-spot-password', username='admin'))
        with migrated.connect() as db:
            self.assertIsNone(db.execute("SELECT value FROM settings WHERE key='password'").fetchone())


if __name__ == '__main__':
    unittest.main()
