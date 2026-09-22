#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


def run(*arguments):
    return subprocess.run(arguments, check=True, text=True, stdout=subprocess.PIPE).stdout


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: verify-native-android.py AAR LLVM_READELF')
    aar = Path(sys.argv[1])
    readelf = Path(sys.argv[2])
    required_files = {
        'assets/LICENSE-AGPL-3.0',
        'assets/ANDROID-NDK-LLVM-NOTICE',
        'assets/HARFBUZZ-COPYING',
        'assets/PCRE2-LICENCE.md',
        'assets/THIRD-PARTY-NOTICES.md',
        'prefab/modules/digitalkhatt/include/digitalkhatt/engine.h',
    }
    required_symbols = {
        'dk_engine_abi_version',
        'dk_engine_create_from_memory',
        'dk_engine_shape_page_utf16_v1',
        'dk_engine_emit_glyph_outline_v1',
    }
    expected_abis = {'arm64-v8a', 'x86_64'}

    with ZipFile(aar) as archive, TemporaryDirectory(prefix='digitalkhatt-aar-') as temporary:
        names = set(archive.namelist())
        missing = required_files - names
        if missing:
            raise RuntimeError(f'AAR is missing: {sorted(missing)}')
        prefab = json.loads(archive.read('prefab/prefab.json'))
        if prefab.get('schema_version') != 2:
            raise RuntimeError('unexpected Prefab schema')
        abis = {
            name.split('/')[4].removeprefix('android.')
            for name in names
            if name.startswith('prefab/modules/digitalkhatt/libs/android.')
            and name.endswith('/libdigitalkhatt.so')
        }
        if abis != expected_abis:
            raise RuntimeError(f'unexpected Android ABIs: {sorted(abis)}')
        root = Path(temporary)
        for abi in sorted(abis):
            name = f'prefab/modules/digitalkhatt/libs/android.{abi}/libdigitalkhatt.so'
            library = root / abi / 'libdigitalkhatt.so'
            library.parent.mkdir()
            library.write_bytes(archive.read(name))
            symbols = run(str(readelf), '--dyn-syms', '--wide', str(library))
            absent = required_symbols - {symbol for symbol in required_symbols if symbol in symbols}
            if absent:
                raise RuntimeError(f'{abi} is missing symbols: {sorted(absent)}')
            segments = run(str(readelf), '--segments', '--wide', str(library))
            alignments = [
                int(line.split()[-1], 16)
                for line in segments.splitlines()
                if line.lstrip().startswith('LOAD ')
            ]
            if not alignments or min(alignments) < 0x4000:
                raise RuntimeError(f'{abi} does not use 16 KiB ELF alignment')
    print(f'Validated Android Prefab AAR for {", ".join(sorted(expected_abis))}')


if __name__ == '__main__':
    main()
