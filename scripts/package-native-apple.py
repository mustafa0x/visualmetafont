#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT
CMAKE_SOURCE = ROOT / 'packages/apple'
BUILD = ROOT / 'build/native-runtime-apple'
OUT = ROOT / 'dist/native-runtime'
DEFAULT_PCRE2 = BUILD / 'pcre2'
PCRE2 = Path(os.environ.get('PCRE2_SOURCE_DIR', DEFAULT_PCRE2)).resolve()
PCRE2_REVISION = 'f454e231fe5006dd7ff8f4693fd2b8eb94333429'


def run(*arguments, cwd=None, capture=False):
    result = subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        text=capture,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ''


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_apple_archive(path):
    data = bytearray(path.read_bytes())
    if data[:8] != b'!<arch>\n' or len(data) < 68:
        raise RuntimeError(f'unexpected Apple static archive: {path}')
    header = data[8:68]
    name_field = bytes(header[:16]).decode('ascii').strip()
    if not name_field.startswith('#1/'):
        raise RuntimeError(f'archive has no extended symbol-table name: {path}')
    name_length = int(name_field.removeprefix('#1/'))
    member_size = int(bytes(header[48:58]).decode('ascii').strip())
    payload_start = 68 + name_length
    payload_end = 68 + member_size
    payload = data[payload_start:payload_end]
    ranlib_bytes = struct.unpack_from('<I', payload, 0)[0]
    entries_end = 4 + ranlib_bytes
    string_bytes = struct.unpack_from('<I', payload, entries_end)[0]
    strings_start = entries_end + 4
    strings_end = strings_start + string_bytes
    if strings_end != len(payload):
        raise RuntimeError(f'unexpected Apple archive symbol table: {path}')
    used_end = 0
    for offset in range(4, entries_end, 8):
        string_offset = struct.unpack_from('<I', payload, offset)[0]
        terminator = payload.index(0, strings_start + string_offset, strings_end)
        used_end = max(used_end, terminator + 1)
    data[payload_start + used_end:payload_start + strings_end] = b'\0' * (strings_end - used_end)
    offset = 8
    while offset < len(data):
        if data[offset + 58:offset + 60] != b'`\n':
            raise RuntimeError(f'invalid Apple archive member header: {path}')
        size = int(bytes(data[offset + 48:offset + 58]).decode('ascii').strip())
        data[offset + 16:offset + 28] = b'0'.ljust(12)
        offset += 60 + size + (size % 2)
    if offset != len(data):
        raise RuntimeError(f'invalid Apple archive member sizes: {path}')
    path.write_bytes(data)


def create_reproducible_zip(source, destination):
    with ZipFile(destination, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted([source, *source.rglob('*')]):
            relative = Path(source.name) / path.relative_to(source)
            name = relative.as_posix() + ('/' if path.is_dir() else '')
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = ((0o755 if path.is_dir() else 0o644) & 0xFFFF) << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, b'' if path.is_dir() else path.read_bytes())


def verify_consumer_link(archive, temporary):
    consumer = temporary / 'consumer'
    consumer.mkdir()
    with ZipFile(archive) as package:
        package.extractall(consumer)
    source = consumer / 'consumer.c'
    source.write_text(
        '#include <digitalkhatt/engine.h>\n'
        'uint32_t consumer_abi(void) { return dk_engine_abi_version(); }\n'
    )
    framework = consumer / 'DigitalKhattEngine.xcframework'
    for sdk, target, slice_name in [
        ('iphoneos', 'arm64-apple-ios15.0', 'ios-arm64'),
        ('iphonesimulator', 'arm64-apple-ios15.0-simulator', 'ios-arm64_x86_64-simulator'),
        ('iphonesimulator', 'x86_64-apple-ios15.0-simulator', 'ios-arm64_x86_64-simulator'),
    ]:
        slice_path = framework / slice_name
        library = next(slice_path.glob('*.a'))
        run(
            'xcrun', '--sdk', sdk, 'clang++', '-target', target, '-dynamiclib',
            '-x', 'c', str(source), '-x', 'none', str(library),
            '-I', str(slice_path / 'Headers'),
            '-o', str(consumer / f'consumer-{target}.dylib'),
        )
    print('Validated Apple consumer links for device arm64 and simulator arm64/x86_64')
    if any(framework.glob('*/Headers/module.modulemap')):
        raise RuntimeError('root module.modulemap collides with other XCFrameworks in Xcode')
    wrapper = consumer / 'Sources/DigitalKhattEngine'
    (wrapper / 'include').mkdir(parents=True)
    (wrapper / 'include/DigitalKhattEngine.h').write_text('#include <digitalkhatt/engine.h>\n')
    (wrapper / 'empty.c').write_text('#include "DigitalKhattEngine.h"\n')
    swift_source = consumer / 'Sources/Probe/main.swift'
    swift_source.parent.mkdir(parents=True)
    swift_source.write_text(
        'import DigitalKhattEngine\n'
        '@main struct Probe { static func main() { print(dk_engine_abi_version()) } }\n'
    )
    (consumer / 'Package.swift').write_text(
        '// swift-tools-version: 6.0\n'
        'import PackageDescription\n'
        'let package = Package(name: "DigitalKhattConsumer", platforms: [.iOS(.v15)], '
        'products: [.executable(name: "Probe", targets: ["Probe"])], '
        'targets: [.binaryTarget(name: "DigitalKhattBinary", '
        'path: "DigitalKhattEngine.xcframework"), '
        '.target(name: "DigitalKhattEngine", dependencies: ["DigitalKhattBinary"], '
        'path: "Sources/DigitalKhattEngine", publicHeadersPath: "include"), '
        '.executableTarget(name: "Probe", dependencies: ["DigitalKhattEngine"])])\n'
    )
    for sdk, target in [
        ('iphoneos', 'arm64-apple-ios15.0'),
        ('iphonesimulator', 'arm64-apple-ios15.0-simulator'),
        ('iphonesimulator', 'x86_64-apple-ios15.0-simulator'),
    ]:
        sdk_path = run('xcrun', '--sdk', sdk, '--show-sdk-path', capture=True)
        run('xcrun', 'swift', 'build', '--triple', target, '--sdk', sdk_path,
            '--product', 'Probe', cwd=consumer)
    print('Validated SwiftPM wrapper imports and links for all Apple slices')


def verify_pcre2():
    run(sys.executable, str(ROOT / 'scripts/verify-pcre2-source.py'), str(PCRE2))


def prepare_pcre2():
    if os.environ.get('PCRE2_SOURCE_DIR'):
        verify_pcre2()
        return
    if not PCRE2.exists():
        PCRE2.parent.mkdir(parents=True, exist_ok=True)
        run('git', 'clone', '--filter=blob:none', 'https://github.com/PCRE2Project/pcre2.git', str(PCRE2))
    run('git', '-C', str(PCRE2), 'fetch', '--depth=1', 'origin', PCRE2_REVISION)
    run('git', '-C', str(PCRE2), 'checkout', '--detach', PCRE2_REVISION)
    actual = run('git', '-C', str(PCRE2), 'rev-parse', 'HEAD', capture=True)
    if actual != PCRE2_REVISION:
        raise RuntimeError(f'PCRE2 must be {PCRE2_REVISION}; got {actual}')
    verify_pcre2()


def configure_and_build(name, sdk, architecture):
    destination = BUILD / name
    if destination.exists():
        shutil.rmtree(destination)
    run(
        'cmake', '-S', str(CMAKE_SOURCE), '-B', str(destination), '-G', 'Ninja',
        '-DCMAKE_SYSTEM_NAME=iOS', f'-DCMAKE_OSX_SYSROOT={sdk}',
        f'-DCMAKE_OSX_ARCHITECTURES={architecture}',
        '-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0', '-DCMAKE_BUILD_TYPE=Release',
        f'-DDIGITALKHATT_SOURCE_DIR={SOURCE}',
        f'-DFETCHCONTENT_SOURCE_DIR_PCRE2={PCRE2}',
        '-DFETCHCONTENT_FULLY_DISCONNECTED=ON',
    )
    run('cmake', '--build', str(destination), '--target', 'digitalkhatt_merged',
        '--parallel', str(os.cpu_count() or 4))
    archive = destination / 'libdigitalkhatt_engine_merged.a'
    normalize_apple_archive(archive)
    return archive


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', sys.argv[1]):
        raise SystemExit('usage: package-native-apple.py VERSION')
    version = sys.argv[1]
    prepare_pcre2()
    device = configure_and_build('ios-arm64', 'iphoneos', 'arm64')
    simulator_arm = configure_and_build('simulator-arm64', 'iphonesimulator', 'arm64')
    simulator_x86 = configure_and_build('simulator-x86_64', 'iphonesimulator', 'x86_64')
    simulator = BUILD / 'libdigitalkhatt_engine_simulator.a'
    run('xcrun', 'lipo', '-create', str(simulator_arm), str(simulator_x86), '-output', str(simulator))

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='digitalkhatt-xcframework-') as temporary_name:
        temporary = Path(temporary_name)
        headers = temporary / 'Headers/digitalkhatt'
        headers.mkdir(parents=True)
        shutil.copyfile(
            SOURCE / 'lib/digitalkhatt/runtime/include/digitalkhatt/engine.h',
            headers / 'engine.h',
        )
        framework = temporary / 'DigitalKhattEngine.xcframework'
        run(
            'xcodebuild', '-create-xcframework',
            '-library', str(device), '-headers', str(headers.parent),
            '-library', str(simulator), '-headers', str(headers.parent),
            '-output', str(framework),
        )
        run('xcrun', 'lipo', str(device), '-verify_arch', 'arm64')
        run('xcrun', 'lipo', str(simulator), '-verify_arch', 'arm64')
        run('xcrun', 'lipo', str(simulator), '-verify_arch', 'x86_64')
        symbols = run('nm', '-gU', str(device), capture=True)
        for symbol in [
            '_dk_engine_abi_version',
            '_dk_engine_create_from_memory',
            '_dk_engine_shape_page_utf16_v1',
            '_dk_engine_emit_glyph_outline_v1',
        ]:
            if symbol not in symbols:
                raise RuntimeError(f'Apple archive is missing {symbol}')
        info = framework / 'Info.plist'
        with info.open('rb') as source_info:
            metadata = plistlib.load(source_info)
        metadata['AvailableLibraries'].sort(key=lambda entry: entry['LibraryIdentifier'])
        with info.open('wb') as normalized_info:
            plistlib.dump(metadata, normalized_info)
        archive = OUT / f'DigitalKhattEngine-{version}.xcframework.zip'
        if archive.exists():
            archive.unlink()
        create_reproducible_zip(framework, archive)
        run('unzip', '-tq', str(archive))
        verify_consumer_link(archive, temporary)
        checksum = run('swift', 'package', 'compute-checksum', str(archive), capture=True)
        if checksum != sha256(archive):
            raise RuntimeError('SwiftPM checksum differs from SHA-256')
        archive.with_suffix(archive.suffix + '.sha256').write_text(f'{checksum}  {archive.name}\n')
        print(f'Packaged {archive}')


if __name__ == '__main__':
    main()
