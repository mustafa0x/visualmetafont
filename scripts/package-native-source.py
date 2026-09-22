#!/usr/bin/env python3
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist/native-runtime'
HARFBUZZ_PATH = Path('lib/harfbuzz/harfbuzz')
PCRE2_REVISION = 'f454e231fe5006dd7ff8f4693fd2b8eb94333429'


def output(*arguments, cwd=ROOT):
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def extract_git_archive(repository, revision, destination, paths=()):
    destination.mkdir(parents=True, exist_ok=True)
    command = ['git', '-C', str(repository), 'archive', '--format=tar', revision]
    if paths:
        command += ['--', *paths]
    archive = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    with tempfile.NamedTemporaryFile() as temporary:
        temporary.write(archive)
        temporary.flush()
        with tarfile.open(temporary.name) as source:
            source.extractall(destination, filter='data')


def normalized(info):
    info.uid = info.gid = 0
    info.uname = info.gname = ''
    info.mtime = 0
    return info


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', sys.argv[1]):
        raise SystemExit('usage: package-native-source.py VERSION')
    version = sys.argv[1]
    source_revision = output('git', 'rev-parse', 'HEAD')
    expected_harfbuzz = output('git', 'rev-parse', f'HEAD:{HARFBUZZ_PATH}')
    actual_harfbuzz = output('git', 'rev-parse', 'HEAD', cwd=ROOT / HARFBUZZ_PATH)
    if actual_harfbuzz != expected_harfbuzz:
        raise RuntimeError(
            f'HarfBuzz must be {expected_harfbuzz}; got {actual_harfbuzz}'
        )

    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / f'digitalkhatt-native-runtime-{version}-source.tar.gz'
    with tempfile.TemporaryDirectory(prefix='digitalkhatt-source-') as temporary_name:
        temporary = Path(temporary_name)
        bundle = temporary / f'digitalkhatt-native-runtime-{version}'
        extract_git_archive(ROOT, 'HEAD', bundle, (
            '.github/workflows/native-runtime.yml',
            '.gitmodules',
            'LICENSE',
            'README.md',
            'lib/digitalkhatt',
            'lib/harfbuzz/CMakeLists.txt',
            'packages',
            'scripts',
        ))
        harfbuzz = bundle / HARFBUZZ_PATH
        if harfbuzz.exists():
            shutil.rmtree(harfbuzz)
        extract_git_archive(ROOT / HARFBUZZ_PATH, 'HEAD', harfbuzz, (
            'CMakeLists.txt',
            'COPYING',
            'README.md',
            'replace-enum-strings.cmake',
            'src',
            'util/Makefile.sources',
        ))

        pcre2_checkout = temporary / 'pcre2-checkout'
        subprocess.run(
            ['git', 'clone', '--filter=blob:none', '--no-checkout',
             'https://github.com/PCRE2Project/pcre2.git', str(pcre2_checkout)],
            check=True,
        )
        subprocess.run(
            ['git', '-C', str(pcre2_checkout), 'fetch', '--depth=1',
             'origin', PCRE2_REVISION],
            check=True,
        )
        pcre2 = bundle / 'third_party/pcre2'
        extract_git_archive(pcre2_checkout, PCRE2_REVISION, pcre2)
        subprocess.run(
            [sys.executable, str(ROOT / 'scripts/verify-pcre2-source.py'), str(pcre2)],
            check=True,
        )

        revisions = {
            'digitalkhatt': source_revision,
            'harfbuzz': expected_harfbuzz,
            'pcre2': PCRE2_REVISION,
        }
        (bundle / 'SOURCE-REVISIONS.json').write_text(
            json.dumps(revisions, indent=2, sort_keys=True) + '\n'
        )
        (bundle / 'BUILDING-NATIVE-RUNTIME.md').write_text(
            '# Building the experimental native runtime\n\n'
            'This archive is the complete corresponding source for the attached '
            'experimental Android and Apple binaries. It includes the exact '
            'DigitalKhatt, HarfBuzz, and PCRE2 source revisions. It intentionally '
            'excludes fonts and Quran corpora; package builds disable the standalone '
            'font-based conformance tests.\n\n'
            'The release workflow uses CMake 3.28.3, Ninja 1.11.1.1, Android NDK '
            '27.1.12297006, Java 21, macOS 14, and Xcode 16.2. To force the Android '
            'or Apple package build to use the bundled PCRE2 source without network '
            'access, set `PCRE2_SOURCE_DIR="$PWD/third_party/pcre2"` before running '
            'the corresponding `scripts/package-native-*.{sh,py}` command.\n\n'
            'To repeat the release workflow conformance tests, obtain its test-only '
            'font from the pinned source revision without adding it to a package:\n\n'
            '```sh\n'
            f'curl -fL https://raw.githubusercontent.com/mustafa0x/visualmetafont/{source_revision}/examples/testvarfont/digitalkhatt-cff2.otf -o /tmp/digitalkhatt-cff2.otf\n'
            "echo 'b816044399d3d2e1c0cef8245a3be997d1d3c48d35486f0448d2473d7e81b132  /tmp/digitalkhatt-cff2.otf' | shasum -a 256 --check\n"
            'cmake -S lib/digitalkhatt/runtime -B build/native-runtime -G Ninja '
            '-DCMAKE_BUILD_TYPE=Release '
            '-DDIGITALKHATT_ENGINE_TEST_FONT=/tmp/digitalkhatt-cff2.otf '
            '-DFETCHCONTENT_SOURCE_DIR_PCRE2="$PWD/third_party/pcre2" '
            '-DFETCHCONTENT_FULLY_DISCONNECTED=ON\n'
            'cmake --build build/native-runtime --parallel\n'
            'ctest --test-dir build/native-runtime --output-on-failure\n'
            '```\n\n'
            'This procedure identifies the exact workflow input; it does not assert '
            'font redistribution rights. Review its provenance before redistributing it.\n'
        )

        with archive.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode='w') as destination:
                    destination.add(bundle, arcname=bundle.name, filter=normalized)
    print(f'Packaged {archive}')


if __name__ == '__main__':
    main()
