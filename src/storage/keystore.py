"""
src/storage/keystore.py
-----------------------
The encryption key for session files.

  - created on first use with Fernet (AES-128-CBC + HMAC-SHA256)
  - stored in <data_dir>/keys/neurosync.key, OUTSIDE the project folder:
    a key inside the repository would end up on GitHub (this happened in v1)
  - file permissions restricted to the current user where the OS supports it
  - rotation: SessionStore.rotate_key() re-encrypts every file with a new key

Losing the key means losing the sessions – back it up separately from the data.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

from src.config import PROJECT_ROOT, data_dir

KEY_FILE = "neurosync.key"


class KeyStoreError(RuntimeError):
    pass


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


class KeyStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root is not None else data_dir() / "keys"
        if _is_inside(self.root, PROJECT_ROOT):
            raise KeyStoreError(
                f"Refusing to store the encryption key inside the project folder ({self.root}). "
                "Set NEUROSYNC_DATA_DIR to a folder outside the repository."
            )
        self.path = self.root / KEY_FILE

    def get_key(self) -> bytes:
        """Return the key, creating it (with restricted permissions) on first use."""
        if self.path.exists():
            return self.path.read_bytes().strip()
        self.root.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        self._write(key)
        return key

    def fernet(self) -> Fernet:
        return Fernet(self.get_key())

    def replace_key(self, new_key: bytes) -> None:
        """Overwrite the stored key (used by SessionStore.rotate_key after re-encryption)."""
        Fernet(new_key)  # validates the format
        self._write(new_key)

    def _write(self, key: bytes) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(key)
        try:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600; best effort on Windows
        except OSError:
            pass
        os.replace(tmp, self.path)
