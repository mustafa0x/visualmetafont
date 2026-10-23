#include <digitalkhatt/engine.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <future>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}

using Engine = std::unique_ptr<dk_engine_t, decltype(&dk_engine_destroy)>;
using Page = std::unique_ptr<dk_page_t, decltype(&dk_page_destroy)>;

// Frozen web Old Madinah page 604, line 4; includes kaf/noon elongation.
const std::u16string text = u"وَلَمْ يُولَدْ ۝٣ وَلَمْ يَكُن لَّهُۥ كُفُوًا ا͏ٔ͏َحَدُۢ ۝٤";

dk_page_options_v1_t options() {
  return {DK_PAGE_OPTIONS_V1_SIZE, DK_PAGE_PROFILE_MADINAH_1405_V1,
          0, 16700, sizeof(dk_page_line_input_v1_t)};
}

dk_page_line_input_v1_t input() {
  return {DK_PAGE_LINE_INPUT_V1_SIZE, 0,
          reinterpret_cast<const uint16_t*>(text.data()), text.size(),
          13961, DK_PAGE_LINE_ROLE_ORDINARY, DK_PAGE_ALIGNMENT_DISTRIBUTE};
}

Page shape(dk_engine_t* engine) {
  auto config = options();
  auto line = input();
  dk_page_t* raw = nullptr;
  require(dk_engine_shape_page_utf16_v1(engine, &config, &line, 1, &raw) ==
              DK_STATUS_OK && raw,
          "shape Old Madinah line");
  return {raw, dk_page_destroy};
}

uint64_t mix(uint64_t digest, uint64_t value) {
  for (unsigned byte = 0; byte < 8; ++byte) {
    digest ^= (value >> (byte * 8)) & UINT64_C(255);
    digest *= UINT64_C(1099511628211);
  }
  return digest;
}

uint64_t inspect(const dk_page_t* page) {
  require(dk_page_line_count(page) == 1, "line count");
  dk_page_line_v1_t line{};
  line.struct_size = DK_PAGE_LINE_V1_SIZE;
  require(dk_page_get_line_v1(page, 0, &line) == DK_STATUS_OK &&
              line.glyph_count == 58 && line.font_scale == 1 &&
              std::abs(line.final_width - 13961) < 1e-8,
          "line geometry");
  uint64_t digest = UINT64_C(1469598103934665603);
  double width = 0;
  for (size_t index = 0; index < line.glyph_count; ++index) {
    dk_page_glyph_v1_t glyph{};
    glyph.struct_size = DK_PAGE_GLYPH_V1_SIZE;
    require(dk_page_get_glyph_v1(page, 0, index, &glyph) == DK_STATUS_OK &&
                glyph.glyph_id != 0 && glyph.cluster < text.size() &&
                glyph.left_tatweel == 0 && glyph.right_tatweel == 0 &&
                std::isfinite(glyph.x_advance) && std::isfinite(glyph.x_offset),
            "static-font glyph");
    digest = mix(mix(digest, glyph.glyph_id), glyph.cluster);
    width += glyph.x_advance;
  }
  require(std::abs(width - line.final_width) < 1e-8, "fractional width sum");
  return digest;
}

dk_status_t move_to(void* data, float, float) {
  ++*static_cast<unsigned*>(data);
  return DK_STATUS_OK;
}
dk_status_t line_to(void* data, float, float) { return move_to(data, 0, 0); }
dk_status_t quadratic_to(void* data, float, float, float, float) {
  return move_to(data, 0, 0);
}
dk_status_t cubic_to(void* data, float, float, float, float, float, float) {
  return move_to(data, 0, 0);
}
dk_status_t close_path(void* data) { return move_to(data, 0, 0); }

void check_fractional_scale(dk_engine_t* engine) {
  dk_line_request_v1_t request{DK_LINE_REQUEST_V1_SIZE, 0,
      reinterpret_cast<const uint16_t*>(text.data()), text.size(), 0};
  dk_line_t* raw_line = nullptr;
  require(dk_engine_shape_line_v1(engine, &request, &raw_line) == DK_STATUS_OK,
          "fractional baseline");
  const std::unique_ptr<dk_line_t, decltype(&dk_line_destroy)> baseline{
      raw_line, dk_line_destroy};
  dk_line_metrics_v1_t metrics{};
  metrics.struct_size = DK_LINE_METRICS_V1_SIZE;
  require(dk_line_get_metrics_v1(baseline.get(), &metrics) == DK_STATUS_OK,
          "fractional baseline width");
  const double expected_scale = 8000.0 / metrics.width;
  auto config = options();
  auto line = input();
  line.desired_width = 8000;
  dk_page_t* raw_page = nullptr;
  require(dk_engine_shape_page_utf16_v1(engine, &config, &line, 1, &raw_page) ==
              DK_STATUS_OK, "fractional page");
  const Page page{raw_page, dk_page_destroy};
  dk_page_line_v1_t shaped{};
  shaped.struct_size = DK_PAGE_LINE_V1_SIZE;
  require(dk_page_get_line_v1(page.get(), 0, &shaped) == DK_STATUS_OK &&
              shaped.glyph_count == metrics.glyph_count &&
              std::abs(shaped.font_scale - expected_scale) < 1e-12 &&
              std::abs(shaped.final_width - 8000) < 1e-8,
          "fractional page scale and width");
  for (size_t index = 0; index < shaped.glyph_count; ++index) {
    dk_glyph_v1_t original{};
    original.struct_size = DK_GLYPH_V1_SIZE;
    dk_page_glyph_v1_t glyph{};
    glyph.struct_size = DK_PAGE_GLYPH_V1_SIZE;
    require(dk_line_get_glyph_v1(baseline.get(), shaped.glyph_count - index - 1,
                                 &original) == DK_STATUS_OK &&
                dk_page_get_glyph_v1(page.get(), 0, index, &glyph) == DK_STATUS_OK &&
                original.glyph_id == glyph.glyph_id &&
                std::abs(original.x_advance * expected_scale - glyph.x_advance) < 1e-9 &&
                std::abs(original.x_offset * expected_scale - glyph.x_offset) < 1e-9 &&
                std::abs(original.y_offset * expected_scale - glyph.y_offset) < 1e-9,
            "scale advances and offsets only after shaping");
  }
}

void check_decoration_scale(dk_engine_t* engine) {
  const std::u16string heading = u"سُورَةُ ٱلْفَاتِحَةِ";
  const std::u16string basmala = u"بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ";
  auto config = options();
  auto narrow = input();
  narrow.desired_width = 8000;
  const dk_page_line_input_v1_t lines[] = {
      narrow,
      {DK_PAGE_LINE_INPUT_V1_SIZE, 0,
       reinterpret_cast<const uint16_t*>(heading.data()), heading.size(), 0,
       DK_PAGE_LINE_ROLE_SURAH_HEADING, DK_PAGE_ALIGNMENT_CENTER},
      {DK_PAGE_LINE_INPUT_V1_SIZE, 0,
       reinterpret_cast<const uint16_t*>(basmala.data()), basmala.size(), 0,
       DK_PAGE_LINE_ROLE_BASMALA, DK_PAGE_ALIGNMENT_CENTER}};
  dk_page_t* raw = nullptr;
  require(dk_engine_shape_page_utf16_v1(engine, &config, lines, 3, &raw) ==
              DK_STATUS_OK, "decorative lines");
  const Page page{raw, dk_page_destroy};
  for (size_t index = 1; index < 3; ++index) {
    dk_page_line_v1_t line{};
    line.struct_size = DK_PAGE_LINE_V1_SIZE;
    require(dk_page_get_line_v1(page.get(), index, &line) == DK_STATUS_OK &&
                line.font_scale == 0.9 && line.final_width > 0 &&
                std::abs(line.x_origin - (16700 - line.final_width) / 2) < 1e-9,
            "decorative scale is independent of body page shrink");
  }
}

void check_lam_pairs(dk_engine_t* engine) {
  for (const auto* value : {u"لَدْ", u"لَذْ", u"لَا", u"لَمْ"}) {
    const std::u16string pair = value;
    dk_line_request_v1_t request{DK_LINE_REQUEST_V1_SIZE, 0,
        reinterpret_cast<const uint16_t*>(pair.data()), pair.size(), 0};
    dk_line_t* raw_line = nullptr;
    require(dk_engine_shape_line_v1(engine, &request, &raw_line) == DK_STATUS_OK,
            "shape unexpanded lam pair");
    const std::unique_ptr<dk_line_t, decltype(&dk_line_destroy)> baseline{
        raw_line, dk_line_destroy};
    auto config = options();
    dk_page_line_input_v1_t line{DK_PAGE_LINE_INPUT_V1_SIZE, 0,
        request.text, request.text_length, 3000,
        DK_PAGE_LINE_ROLE_ORDINARY, DK_PAGE_ALIGNMENT_DISTRIBUTE};
    dk_page_t* raw_page = nullptr;
    require(dk_engine_shape_page_utf16_v1(engine, &config, &line, 1, &raw_page) ==
                DK_STATUS_OK, "justify lam pair");
    const Page page{raw_page, dk_page_destroy};
    dk_line_metrics_v1_t metrics{};
    metrics.struct_size = DK_LINE_METRICS_V1_SIZE;
    dk_page_line_v1_t shaped{};
    shaped.struct_size = DK_PAGE_LINE_V1_SIZE;
    require(dk_line_get_metrics_v1(baseline.get(), &metrics) == DK_STATUS_OK &&
                dk_page_get_line_v1(page.get(), 0, &shaped) == DK_STATUS_OK &&
                metrics.glyph_count == shaped.glyph_count,
            "lam pair glyph count");
    for (size_t index = 0; index < shaped.glyph_count; ++index) {
      dk_glyph_v1_t original{};
      original.struct_size = DK_GLYPH_V1_SIZE;
      dk_page_glyph_v1_t glyph{};
      glyph.struct_size = DK_PAGE_GLYPH_V1_SIZE;
      require(dk_line_get_glyph_v1(baseline.get(), shaped.glyph_count - index - 1,
                                   &original) == DK_STATUS_OK &&
                  dk_page_get_glyph_v1(page.get(), 0, index, &glyph) == DK_STATUS_OK &&
                  original.glyph_id == glyph.glyph_id,
              "Old Madinah must not stretch lam/dal or lam/dhal");
    }
  }
}

}  // namespace

int main(int argc, char** argv) {
  try {
    require(argc == 3, "expected static Old Madinah and dynamic New Madinah fonts");
    dk_engine_t* raw = reinterpret_cast<dk_engine_t*>(uintptr_t{1});
    require(dk_engine_create_from_file(argv[1], &raw) == DK_STATUS_UNSUPPORTED_FONT &&
                raw == nullptr,
            "legacy constructor must remain strict");
    require(dk_engine_create_from_file_for_profile_v1(
                argv[1], DK_PAGE_PROFILE_MADINAH_1405_V1, &raw) == DK_STATUS_OK,
            "explicit static-font engine");
    Engine file_engine{raw, dk_engine_destroy};
    require(dk_engine_upem(file_engine.get()) == 1000, "Old Madinah UPEM");
    require(dk_engine_create_from_file_for_profile_v1(
                argv[2], DK_PAGE_PROFILE_MADINAH_1405_V1, &raw) ==
                DK_STATUS_UNSUPPORTED_FONT && raw == nullptr,
            "dynamic font cannot select static profile");
    require(dk_engine_create_from_file_for_profile_v1(
                argv[1], 0, &raw) == DK_STATUS_INVALID_ARGUMENT && raw == nullptr,
            "unknown creation profile");
    require(dk_engine_create_from_file_for_profile_v1(
                argv[1], DK_PAGE_PROFILE_MADINAH_1405_V1, nullptr) ==
                DK_STATUS_INVALID_ARGUMENT,
            "null constructor output");

    std::ifstream stream(argv[1], std::ios::binary);
    std::vector<char> bytes{std::istreambuf_iterator<char>{stream}, {}};
    require(!bytes.empty(), "static font bytes");
    require(dk_engine_create_from_memory_for_profile_v1(
                bytes.data(), bytes.size(), DK_PAGE_PROFILE_MADINAH_1405_V1,
                &raw) == DK_STATUS_OK, "memory static-font engine");
    Engine memory_engine{raw, dk_engine_destroy};
    require(dk_engine_create_from_memory(bytes.data(), bytes.size(), &raw) ==
                DK_STATUS_UNSUPPORTED_FONT && raw == nullptr,
            "legacy memory constructor must remain strict");
    require(dk_engine_create_from_memory_for_profile_v1(
                bytes.data(), bytes.size(), UINT32_MAX, &raw) ==
                DK_STATUS_INVALID_ARGUMENT && raw == nullptr,
            "unknown memory creation profile");
    // Removing a required static table must still fail.
    const std::string table_tag = "GSUB";
    const auto table = std::search(bytes.begin(), bytes.end(), table_tag.begin(), table_tag.end());
    require(table != bytes.end(), "static GSUB record");
    *table = 'X';
    require(dk_engine_create_from_memory_for_profile_v1(
                bytes.data(), bytes.size(), DK_PAGE_PROFILE_MADINAH_1405_V1,
                &raw) == DK_STATUS_UNSUPPORTED_FONT && raw == nullptr,
            "reject incomplete static font");
    std::fill(bytes.begin(), bytes.end(), 0);
    check_lam_pairs(file_engine.get());
    check_fractional_scale(file_engine.get());
    check_decoration_scale(file_engine.get());
    auto page = shape(file_engine.get());
    const auto expected = inspect(page.get());
    // Glyph/cluster digest generated from the frozen web reference, not native output.
    require(expected == UINT64_C(0xeab65ddc562cb3bc), "web page 604 glyph/cluster parity");
    auto memory_page = shape(memory_engine.get());
    require(inspect(memory_page.get()) == expected, "memory copies font input");

    std::vector<std::future<uint64_t>> futures;
    for (unsigned i = 0; i < 4; ++i) {
      futures.push_back(std::async(std::launch::async, [&] {
        return inspect(shape(file_engine.get()).get());
      }));
    }
    for (auto& future : futures) require(future.get() == expected, "concurrent static shaping");

    auto config = options();
    config.profile = DK_PAGE_PROFILE_MADINAH_1441_V1;
    auto line = input();
    dk_page_t* raw_page = reinterpret_cast<dk_page_t*>(uintptr_t{1});
    require(dk_engine_shape_page_utf16_v1(file_engine.get(), &config, &line, 1,
                                         &raw_page) == DK_STATUS_INVALID_ARGUMENT &&
                raw_page == nullptr,
            "page profile must match engine profile");

    dk_line_request_v1_t request{DK_LINE_REQUEST_V1_SIZE, 0,
        reinterpret_cast<const uint16_t*>(text.data()), text.size(), 1};
    dk_line_t* raw_line = reinterpret_cast<dk_line_t*>(uintptr_t{1});
    require(dk_engine_shape_line_v1(file_engine.get(), &request, &raw_line) ==
                DK_STATUS_INVALID_ARGUMENT && raw_line == nullptr,
            "static font cannot request JTST");
    request.target_width = 0;
    require(dk_engine_shape_line_v1(file_engine.get(), &request, &raw_line) ==
                DK_STATUS_OK && raw_line, "unjustified static line");
    dk_line_destroy(raw_line);

    unsigned commands = 0;
    dk_path_sink_v1_t sink{DK_PATH_SINK_V1_SIZE, &commands, move_to, line_to,
                           quadratic_to, cubic_to, close_path};
    dk_glyph_variant_v1_t variant{DK_GLYPH_VARIANT_V1_SIZE, 244, 0, 0, 0};
    require(dk_engine_emit_glyph_outline_v1(file_engine.get(), &variant, &sink) ==
                DK_STATUS_OK && commands > 0, "static outline");
    variant.left_tatweel = 0.1;
    require(dk_engine_emit_glyph_outline_v1(file_engine.get(), &variant, &sink) ==
                DK_STATUS_INVALID_ARGUMENT, "static outline cannot vary");

    file_engine.reset();
    memory_engine.reset();
    require(inspect(page.get()) == expected, "static page outlives its engine");
    std::cout << "old_madinah_glyphs=58 digest=" << std::hex << expected << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "Old Madinah conformance failure: " << error.what() << '\n';
    return 1;
  }
}
