#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path
import sys

EXPECTED_REVISION = 'f454e231fe5006dd7ff8f4693fd2b8eb94333429'
EXPECTED_SHA256 = '0d5b12d0b3d82b820bc2e9d3d34b5ea5d849648290a52e0f14b181c31309d371'


def source_digest(root):
    root = Path(root).resolve()
    digest = hashlib.sha256()
    entries = sorted(
        path for path in root.rglob('*')
        if '.git' not in path.relative_to(root).parts and (path.is_file() or path.is_symlink())
    )
    for path in entries:
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            kind = b'L'
            payload = os.readlink(path).encode()
        else:
            kind = b'X' if path.stat().st_mode & 0o111 else b'F'
            payload = path.read_bytes()
        digest.update(kind)
        digest.update(len(relative).to_bytes(4, 'big'))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, 'big'))
        digest.update(payload)
    return digest.hexdigest()


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: verify-pcre2-source.py SOURCE_DIRECTORY')
    source = Path(sys.argv[1])
    if not (source / 'CMakeLists.txt').is_file():
        raise RuntimeError(f'not a PCRE2 source tree: {source}')
    actual = source_digest(source)
    if actual != EXPECTED_SHA256:
        raise RuntimeError(
            f'PCRE2 source must match {EXPECTED_REVISION}; source digest was {actual}'
        )
    print(f'Validated PCRE2 source {EXPECTED_REVISION}')


if __name__ == '__main__':
    main()
