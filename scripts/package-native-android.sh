#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

version="${1:?usage: package-native-android.sh VERSION}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]] || {
  echo "invalid version: $version" >&2
  exit 1
}
: "${ANDROID_NDK_HOME:?ANDROID_NDK_HOME must point to Android NDK 27.1.12297006}"

android="packages/android"
gradle_args=(--no-daemon --no-configuration-cache)
if [ -n "${PCRE2_SOURCE_DIR:-}" ]; then
  [ -d "$PCRE2_SOURCE_DIR" ] || { echo "PCRE2_SOURCE_DIR is not a directory" >&2; exit 1; }
  python3 scripts/verify-pcre2-source.py "$PCRE2_SOURCE_DIR"
  gradle_args+=("-Ppcre2Source=$PCRE2_SOURCE_DIR")
fi
rm -rf "$android/engine/.cxx" "$android/consumer/.cxx"
"$android/gradlew" -p "$android" "${gradle_args[@]}" :engine:clean :engine:assembleRelease
"$android/gradlew" -p "$android" "${gradle_args[@]}" :consumer:clean :consumer:externalNativeBuildRelease

out="dist/native-runtime"
mkdir -p "$out"
aar="$out/digitalkhatt-engine-android-$version.aar"
cp "$android/engine/build/outputs/aar/engine-release.aar" "$aar"

readelf="$(find "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt" -name llvm-readelf -print -quit)"
[ -x "$readelf" ] || { echo "llvm-readelf is unavailable" >&2; exit 1; }
python3 scripts/verify-native-android.py "$aar" "$readelf"

symbols="$out/digitalkhatt-engine-android-$version-symbols.zip"
python3 - "$aar" "$symbols" <<'PY'
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import sys

source, destination = map(Path, sys.argv[1:])
with ZipFile(source) as archive, ZipFile(destination, 'w', ZIP_DEFLATED) as output:
    for name in sorted(item.filename for item in archive.infolist()
                       if item.filename.startswith('prefab/modules/digitalkhatt/libs/')
                       and item.filename.endswith('/libdigitalkhatt.so')):
        abi = name.split('/')[-2].removeprefix('android.')
        output.writestr(f'{abi}/libdigitalkhatt.so', archive.read(name))
PY

python3 - "$aar" "$symbols" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys
for name in sys.argv[1:]:
    path = Path(name)
    path.with_suffix(path.suffix + '.sha256').write_text(
        f'{sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
    )
PY

printf 'Packaged %s\n' "$aar"
