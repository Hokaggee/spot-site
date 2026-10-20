"""Server-only credential file; passwords never enter the public site assets."""
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
from pathlib import Path

ITERATIONS = 600_000


class CredentialFile:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            if self.path.is_symlink():
                return None
            record = json.loads(self.path.read_text())
            if (record.get('algorithm') != 'pbkdf2_sha256'
                    or not isinstance(record.get('username'), str)
                    or not re.fullmatch(r'[A-Za-z0-9_.@-]{3,64}', record['username'])
                    or not isinstance(record.get('iterations'), int)
                    or not 310_000 <= record['iterations'] <= 1_000_000
                    or not isinstance(record.get('salt'), str)
                    or not 8 <= len(record['salt']) <= 128
                    or not re.fullmatch(r'[a-f0-9]{64}', record.get('password_hash', ''))):
                return None
            return record
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def fingerprint(self):
        record = self.read()
        return self.record_fingerprint(record)

    @staticmethod
    def record_fingerprint(record):
        return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest() if record else None

    def write(self, record, replace=False):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError('Файл доступа не должен быть символической ссылкой.')
        descriptor, temporary = tempfile.mkstemp(prefix='.admin-auth-', dir=self.path.parent)
        try:
            with os.fdopen(descriptor, 'w') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(record, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            if replace:
                os.replace(temporary, self.path)
            else:
                try:
                    os.link(temporary, self.path)
                except FileExistsError:
                    raise ValueError('Данные входа уже настроены. Для смены используйте --replace.') from None
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create(self, username, password, replace=False):
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.@-]{3,64}', username):
            raise ValueError('Логин: от 3 до 64 латинских букв, цифр или символов _.@-')
        if not isinstance(password, str) or not 10 <= len(password) <= 256:
            raise ValueError('Пароль должен содержать от 10 до 256 символов.')
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), ITERATIONS).hex()
        self.write({'version': 1, 'username': username, 'algorithm': 'pbkdf2_sha256',
                    'iterations': ITERATIONS, 'salt': salt, 'password_hash': digest}, replace=replace)

    def authenticate(self, username, password):
        record = self.read()
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 256 or len(username) > 64:
            return None
        # Perform the same password derivation for unknown usernames.
        salt = record['salt'] if record else 'unconfigured-spot-admin'
        iterations = record['iterations'] if record else ITERATIONS
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iterations).hex()
        password_ok = hmac.compare_digest(actual, record['password_hash'] if record else '0'*64)
        username_ok = hmac.compare_digest(username.encode(), record['username'].encode() if record else b'')
        return self.record_fingerprint(record) if record and password_ok and username_ok else None

    def verify(self, username, password):
        return self.authenticate(username, password) is not None
