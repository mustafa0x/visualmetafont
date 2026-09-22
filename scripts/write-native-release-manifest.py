#!/usr/bin/env python3
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PCRE2_REVISION = 'f454e231fe5006dd7ff8f4693fd2b8eb94333429'


def git(*arguments):
    return subprocess.run(
        ['git', '-C', str(ROOT), *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def main():
    if len(sys.argv) != 3 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', sys.argv[1]):
        raise SystemExit('usage: write-native-release-manifest.py VERSION ASSET_DIRECTORY')
    version = sys.argv[1]
    assets = Path(sys.argv[2])
    files = []
    for path in sorted(assets.iterdir()):
        if path.is_file() and path.name != 'manifest.json':
            files.append({
                'name': path.name,
                'bytes': path.stat().st_size,
                'sha256': sha256(path.read_bytes()).hexdigest(),
            })
    manifest = {
        'schema': 1,
        'name': 'DigitalKhatt experimental native runtime',
        'version': version,
        'experimental': True,
        'production_distribution': False,
        'license': 'AGPL-3.0-or-later',
        'source': {
            'repository': 'https://github.com/mustafa0x/visualmetafont',
            'revision': git('rev-parse', 'HEAD'),
            'harfbuzz_revision': git('rev-parse', 'HEAD:lib/harfbuzz/harfbuzz'),
            'pcre2_revision': PCRE2_REVISION,
        },
        'engine': {'abi': 1, 'cmake_version': '0.2.0'},
        'toolchains': {
            'android_ndk': '27.1.12297006',
            'cmake': '3.28.3',
            'java': '21',
            'macos_runner': 'macos-14',
            'ninja': '1.11.1.1',
            'xcode': '16.2',
        },
        'files': files,
    }
    (assets / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
