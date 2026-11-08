import logging
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Final

from sqlcipher3 import dbapi2 as sqlcipher  # pylint: disable=no-name-in-module

from rotkehlchen.constants.misc import AUTO_BACKUP_DIR_PREFIX, USERDB_NAME, USERSDIR_NAME
from rotkehlchen.db.dbhandler import DBHandler
from rotkehlchen.db.drivers.sqlite import DBConnection, DBConnectionType
from rotkehlchen.db.misc import detect_sqlcipher_version
from rotkehlchen.db.utils import unlock_database
from rotkehlchen.errors.api import AuthenticationError
from rotkehlchen.errors.misc import (
    SystemPermissionError,
)
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.utils.misc import ts_now

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rotkehlchen.assets.asset import Asset
    from rotkehlchen.db.settings import ModifiableDBSettings
    from rotkehlchen.user_messages import MessagesAggregator

logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

BUFFERSIZE = 64 * 1024
# 6 trades a little size for speed: 9 is ~55% slower for only ~5 MB less on a large DB,
# and levels 12-15 compress no better than 9
BACKUP_ZSTD_LEVEL: Final = 6
BYTES_PER_MB: Final = 1024 * 1024


class DataHandler:

    def __init__(
            self,
            data_directory: Path,
            msg_aggregator: MessagesAggregator,
            sql_vm_instructions_cb: int,
    ):
        self.logged_in = False
        self.data_directory = data_directory
        self.username = 'no_user'
        self.msg_aggregator = msg_aggregator
        self.sql_vm_instructions_cb = sql_vm_instructions_cb

    def _get_user_data_dir(self, username: str) -> Path:
        """Return the user's directory after ensuring the name is one safe path component.

        May raise:
        - SystemPermissionError if the username is not a safe path component within the users
          directory.
        """
        users_dir = self.data_directory / USERSDIR_NAME
        user_data_dir = users_dir / username
        if (
            username in {'.', '..'} or
            PurePosixPath(username).name != username or
            PureWindowsPath(username).name != username or
            user_data_dir.resolve().parent != users_dir.resolve()
        ):
            raise SystemPermissionError(
                f'Data dir for user {username} is not in the users directory. '
                'Usernames may not contain path separators.',
            )

        return user_data_dir

    def check_password(self, username: str, password: str) -> bool:
        """Cheaply verify a user's password without the full unlock.

        Opens the encrypted user DB and applies the sqlcipher key (the same check
        `DBHandler._connect` relies on) but skips migrations/data loading, then
        closes. Used by the `authenticate` endpoint to mint a session token before
        the heavy async login. Must only be called when no user is logged in (the
        authenticate-first flow), since it briefly registers a USER connection.

        Returns True if the password opens the DB, False on a wrong password or a
        missing/unreadable DB.
        """
        try:
            user_db = self._get_user_data_dir(username) / USERDB_NAME
        except SystemPermissionError:
            return False

        if not user_db.exists():
            return False

        try:
            connection = DBConnection(
                path=str(user_db),
                connection_type=DBConnectionType.USER,
                sql_vm_instructions_cb=self.sql_vm_instructions_cb,
            )
        except sqlcipher.OperationalError:  # pylint: disable=no-member
            return False

        try:
            unlock_database(
                db_connection=connection,
                password=password,
                sqlcipher_version=detect_sqlcipher_version(),
                apply_optimizations=False,
            )
        except sqlcipher.DatabaseError:  # pylint: disable=no-member
            return False
        finally:
            connection.close()

        return True

    def logout(self) -> None:
        if self.logged_in:
            self.username = 'no_user'
            self.user_data_dir: Path | None = None
            db = getattr(self, 'db', None)
            if db is not None:
                with self.db.conn.read_ctx() as cursor:
                    self.db.update_owned_assets_in_globaldb(cursor)
                self.db.logout()
            self.logged_in = False

    def unlock(
            self,
            username: str,
            password: str,
            create_new: bool,
            resume_from_backup: bool,
            initial_settings: ModifiableDBSettings | None = None,
    ) -> Path:
        """Unlocks a user, either logging them in or creating a new user

        May raise:
        - SystemPermissionError if there are permission errors when accessing the DB
        or a directory in the user's filesystem
        - AuthenticationError if the given user does not exist, or if
        sqlcipher version problems are detected
        - DBUpgradeError if the rotki DB version is newer than the software or
        there is a DB upgrade and there is an error or if the version is older
        than the one supported.
        - DBSchemaError if database schema is malformed
        """
        user_data_dir = self._get_user_data_dir(username)
        if create_new:
            if username.startswith(AUTO_BACKUP_DIR_PREFIX):  # get_users() would not list it
                raise AuthenticationError(
                    f'Usernames starting with {AUTO_BACKUP_DIR_PREFIX} are reserved for '
                    'backups of failed logins. Choose a different name.',
                )

            try:
                if (user_data_dir / USERDB_NAME).exists():
                    raise AuthenticationError(
                        f'User {username} already exists. User data dir: {user_data_dir}',
                    )

                user_data_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                raise SystemPermissionError(
                    f'Failed to create directory for user: {e!s}',
                ) from e

        else:
            try:
                if not user_data_dir.exists():
                    raise AuthenticationError(f'User {username} does not exist')

                if not (user_data_dir / USERDB_NAME).exists():
                    raise PermissionError

            except PermissionError as e:
                # This is bad. User directory exists but database is missing.
                # Or either DB or user directory can't be accessed due to permissions
                # Make a backup of the directory that user should probably remove
                # on their own. At the same time delete the directory so that a new
                # user account can be created
                shutil.move(
                    user_data_dir,
                    self.data_directory / USERSDIR_NAME / f'{AUTO_BACKUP_DIR_PREFIX}{username}_{ts_now()}',  # noqa: E501
                )

                raise SystemPermissionError(
                    f'User {username} exists but DB is missing. Somehow must have been manually '
                    'deleted or is corrupt or access permissions do not allow reading. '
                    'Please recreate the user account. '
                    'A backup of the user directory was created.',
                ) from e

        self.db: DBHandler = DBHandler(
            user_data_dir=user_data_dir,
            password=password,
            msg_aggregator=self.msg_aggregator,
            initial_settings=initial_settings,
            sql_vm_instructions_cb=self.sql_vm_instructions_cb,
            resume_from_backup=resume_from_backup,
        )
        self.user_data_dir = user_data_dir
        self.logged_in = True
        self.username = username
        return user_data_dir

    def add_ignored_assets(self, assets: Sequence[Asset]) -> tuple[set[Asset], set[Asset]]:
        """Adds ignored assets to the DB.

        Returns the set of assets that have been ignored and the set of assets that were already
        ignored.
        """
        already_ignored, to_ignore = set(), set()
        with self.db.conn.read_ctx() as cursor:
            ignored_asset_ids = self.db.get_ignored_asset_ids(cursor)
            for asset in assets:
                if asset.identifier in ignored_asset_ids:
                    already_ignored.add(asset)
                else:
                    to_ignore.add(asset)

        with self.db.user_write() as write_cursor:
            for asset in to_ignore:
                self.db.add_to_ignored_assets(write_cursor=write_cursor, asset=asset)

        return to_ignore, already_ignored

    def remove_ignored_assets(self, assets: list[Asset]) -> tuple[set[Asset], set[Asset]]:
        """Removes ignored assets from the DB.

        Returns the set of assets that have been unignored and the set of assets that weren't
        ignored.
        """
        not_ignored, to_unignore = set(), set()
        with self.db.conn.read_ctx() as cursor:
            ignored_asset_ids = self.db.get_ignored_asset_ids(cursor)
            for asset in assets:
                if asset.identifier not in ignored_asset_ids:
                    not_ignored.add(asset)
                else:
                    to_unignore.add(asset)

        with self.db.user_write() as write_cursor:
            for asset in to_unignore:
                self.db.remove_from_ignored_assets(write_cursor=write_cursor, asset=asset)

        return to_unignore, not_ignored

    def get_users(self) -> dict[str, str]:
        """Returns a dict with all users in the system.

        Each key is a user's name and the value is denoting whether that
        particular user is logged in or not. Directories moved aside after a failed login or
        account creation are left out, since they are kept only for recovery.
        """
        users = {}
        users_dir = self.data_directory / USERSDIR_NAME
        if not users_dir.exists():
            return {}

        for x in users_dir.iterdir():
            try:
                if (
                    x.is_dir() and
                    not x.name.startswith(AUTO_BACKUP_DIR_PREFIX) and
                    (x / USERDB_NAME).exists()
                ):
                    users[x.name] = 'loggedin' if x.name == self.username else 'loggedout'
            except PermissionError:
                # ignore directories that can't be accessed
                continue

        return users
