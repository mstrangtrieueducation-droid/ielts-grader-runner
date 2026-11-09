"""Encrypt/decrypt the private bundle (prompts, class config) and runner state.

The public repository only ever contains *.enc files; the key lives in the WRITING_BUNDLE_KEY secret.
"""
import io
import os
import sys
import tarfile
from pathlib import Path

from cryptography.fernet import Fernet


def _f():
    key = os.environ.get("WRITING_BUNDLE_KEY", "").strip()
    if not key:
        raise SystemExit("WRITING_BUNDLE_KEY missing")
    return Fernet(key.encode())


def pack_dir(src: Path, dest: Path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(src, arcname=".")
    dest.write_bytes(_f().encrypt(buf.getvalue()))


def unpack_dir(src: Path, dest: Path):
    data = _f().decrypt(src.read_bytes())
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        t.extractall(dest, filter="data")


def seal(data: bytes) -> bytes:
    return _f().encrypt(data)


def open_(data: bytes) -> bytes:
    return _f().decrypt(data)


if __name__ == "__main__":  # python vault.py pack SRC DEST.enc | unpack SRC.enc DEST
    cmd, a, b = sys.argv[1:4]
    (pack_dir if cmd == "pack" else unpack_dir)(Path(a), Path(b))
