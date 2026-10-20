"""Create or rotate server credentials without putting a password in source or CLI args."""
import argparse
import getpass
import os
import secrets
from pathlib import Path

from auth import CredentialFile


def main():
    parser = argparse.ArgumentParser(description='Создать или сменить доступ к админке СПОТа.')
    parser.add_argument('--username', default='admin')
    parser.add_argument('--file', type=Path, default=Path(os.environ.get('SPOT_AUTH_FILE', Path(__file__).resolve().parent / '.spot-data/admin-auth.json')))
    parser.add_argument('--replace', action='store_true', help='Сменить существующий доступ и завершить старые сессии.')
    parser.add_argument('--generate', action='store_true', help='Сгенерировать и показать пароль один раз.')
    args = parser.parse_args()
    password = secrets.token_urlsafe(18) if args.generate else getpass.getpass('Новый пароль (не менее 10 символов): ')
    if not args.generate and password != getpass.getpass('Повторите пароль: '):
        parser.error('Пароли не совпадают.')
    try:
        CredentialFile(args.file).create(args.username, password, replace=args.replace)
    except ValueError as error:
        parser.error(str(error))
    print(f'Файл доступа: {args.file}\nЛогин: {args.username}')
    if args.generate:
        print(f'Пароль (сохраните, повторно он не показывается): {password}')


if __name__ == '__main__':
    main()
