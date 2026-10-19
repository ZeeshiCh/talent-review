"""Atomic private content-addressed audio storage shared by import and candidate APIs."""

import hashlib
import os
import tempfile
from pathlib import Path


class StorageProblem(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_audio(root: Path, payload: bytes, suffix: str = ".m4a") -> str:
    """Atomically publish a private, content-addressed blob; never replace an existing file."""
    if suffix not in {".m4a", ".mp3", ".wav"}:
        raise StorageProblem("Unsupported private audio extension")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = digest(payload) + suffix
    target = root / name
    if target.is_symlink():
        raise StorageProblem("Private audio storage contains an unsafe link")
    if target.exists():
        if digest(target.read_bytes()) != digest(payload):
            raise StorageProblem("Private audio checksum conflict")
        return str(target.resolve())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".import-", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.is_symlink() or digest(target.read_bytes()) != digest(payload):
                raise StorageProblem("Private audio checksum conflict") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return str(target.resolve())
