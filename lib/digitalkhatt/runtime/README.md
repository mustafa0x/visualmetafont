# DigitalKhatt native runtime

This directory provides a small C ABI over DigitalKhatt's HarfBuzz fork. It
loads a compiled CFF2/JTST font, shapes Arabic text, returns glyph placement and
tatweel coordinates, and streams selected CFF2 outlines to renderer-owned
callbacks.

It deliberately excludes Qt, MetaPost, page composition, corpus loading, and
platform UI code. Those belong outside the typography runtime.

## ABI v1

The ABI major remains 1. The `0.2` symbol set adds page typography without
changing any `0.1` symbol or structure.

The low-level line operation:

- shapes one independent RTL Arabic UTF-16 line;
- optionally runs the font's JTST target-width pass;
- does **not** apply a Mushaf page profile or FeatureJustifier page policy.

The additive page operation:

- accepts ordered UTF-16 lines, target widths, semantic roles, and alignment;
- applies a profile-versioned page-wide feature-planning policy;
- returns immutable line and glyph results with fractional final spacing;
- expresses widths and glyph positions in font design units, leaving device
  scaling to the host;
- leaves page breaking, vertical baselines, decorations, interaction, and
  rendering to the host.

`DK_PAGE_PROFILE_MADINAH_1441_V1` maps to the canonical New Madinah
FeatureJustifier policy. Revision 1 does not expose feature records, tajweed
colors, screen coordinates, selection data, or platform paths.

Page input and output records are append-only and size-versioned. Set their
`struct_size` fields to the matching `*_V1_SIZE` constant. The path sink follows
the same convention.

## Font contract

The runtime accepts the two-axis DigitalKhatt runtime profile:

- CFF2, GSUB, GPOS, GDEF, JTST, `fvar`, and HVAR tables;
- exactly two variation axes;
- `LTAT` at axis index 0 and `RTAT` at axis index 1;
- both axes centered on zero with negative and positive ranges.

Tatweel values crossing the ABI are normalized coordinates in `[-1, 1]`.

### Old Madinah development profile

The additive `dk_engine_create_from_file_for_profile_v1` and `dk_engine_create_from_memory_for_profile_v1` constructors accept an explicit page profile. Existing constructors still select New Madinah and retain every runtime-font requirement above; existing structures and ABI major 1 are unchanged.

`DK_PAGE_PROFILE_MADINAH_1405_V1` selects the experimental Old Madinah policy. It accepts static CFF2 fonts with GSUB, GPOS, GDEF, 1000 UPEM, and no JTST, HVAR, or fvar tables. The application must pin the intended font; accepting this table contract does not authenticate an edition. A page's profile must match its engine's creation profile. Static engines reject nonzero JTST line target widths and nonzero outline tatweel coordinates; use the page API for feature-based justification.

Old Madinah follows the browser's final-ascendant, lam/dal, and kaf/noon feature rules without changing New Madinah output. It shapes at the base font size and applies fractional scaling afterward; decorative headings and basmala use an independent 0.9 scale. Opening-page basmala that the host wants justified must be supplied as ordinary text, as in the browser. Corpus loading, Tajweed, baselines, ornaments, hit testing, and platform rendering remain host-owned.

These additions remain experimental development support, not approval for production distribution in Muhaffidh. The release workflow checksum-verifies an external Old Madinah test font and runs its conformance test without bundling the font in SDK artifacts.

## Build and test

```sh
cmake -S lib/digitalkhatt/runtime -B build/digitalkhatt-runtime -G Ninja \
  -DBUILD_SHARED_LIBS=ON
cmake --build build/digitalkhatt-runtime
ctest --test-dir build/digitalkhatt-runtime --output-on-failure
cmake --install build/digitalkhatt-runtime --prefix /your/sdk/prefix
```

Set `DIGITALKHATT_ENGINE_TEST_FONT` to exercise another compatible font. Set
`DIGITALKHATT_ENGINE_PAGE_PARITY_FONT` to a corrected compiler runtime font to
enable the strict page-43 parity fixture (15 lines, 1,352 glyphs, and 1,230
visible outlines).

Set `DIGITALKHATT_ENGINE_OLD_MADINAH_TEST_FONT` to an external static Old Madinah font to enable the pilot test. The tested font is Muhaffidh's `public/dk-fonts/oldmadina.otf`, SHA-256 `86fc18f670aec9de17fe7ad310b8cfd86848c41aa966e09c4bf67f5f083d6174`. It is not bundled in this SDK. The regression freezes web page 604 line 4 glyph/cluster output, verifies strict legacy constructors, file/memory ownership, unsupported contracts, profile mismatch, static outline rules, concurrency, and page lifetime. Ordinary tests still run without that optional external font; enabling the Old Madinah test is required when validating this pilot.

`digitalkhatt_old_madinah_probe FONT INPUT.tsv` emits public-API geometry and base outlines for an external corpus. Muhaffidh's `native/scripts/check_old_madinah_runtime.mjs` drives it against all 604 web pages, including heading/basmala scaling, cluster/variant selection, positioned advances/offsets, and outlines. Integer requested widths permit at most 0.5 font units of placement difference from the web's fractional widths. This does not validate platform page furniture, interaction, or painted Tajweed.

Shared installs export `digitalkhatt::engine` through
`find_package(DigitalKhattEngine CONFIG REQUIRED)`.

The experimental Android Prefab AAR and Apple XCFramework are built from
`packages/` by `.github/workflows/native-runtime.yml`. PCRE2 is pinned to the
exact commit recorded in the build and release manifest; release artifacts do
not resolve a movable dependency tag. The packages contain no font or Quran
corpus.

The runtime inherits this repository's AGPL-3.0-or-later license. Its native
packages are development and evaluation artifacts, not an approval to embed
DigitalKhatt in a privately sourced production application. Review those terms
before distributing any application that links the library.
