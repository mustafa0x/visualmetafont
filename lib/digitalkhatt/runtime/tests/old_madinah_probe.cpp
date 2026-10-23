#include <digitalkhatt/engine.h>
#include <fstream>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Engine = std::unique_ptr<dk_engine_t, decltype(&dk_engine_destroy)>;
using Page = std::unique_ptr<dk_page_t, decltype(&dk_page_destroy)>;
void check(dk_status_t status) {
  if (status != DK_STATUS_OK) throw std::runtime_error(dk_status_message(status));
}
dk_status_t move_to(void* data, float x, float y) {
  *static_cast<std::ostream*>(data) << 'M' << x << ',' << y; return DK_STATUS_OK;
}
dk_status_t line_to(void* data, float x, float y) {
  *static_cast<std::ostream*>(data) << 'L' << x << ',' << y; return DK_STATUS_OK;
}
dk_status_t quadratic_to(void* data, float ax, float ay, float x, float y) {
  *static_cast<std::ostream*>(data) << 'Q' << ax << ',' << ay << ' ' << x << ',' << y; return DK_STATUS_OK;
}
dk_status_t cubic_to(void* data, float ax, float ay, float bx, float by, float x, float y) {
  *static_cast<std::ostream*>(data) << 'C' << ax << ',' << ay << ' ' << bx << ',' << by << ' ' << x << ',' << y; return DK_STATUS_OK;
}
dk_status_t close_path(void* data) {
  *static_cast<std::ostream*>(data) << 'Z'; return DK_STATUS_OK;
}
struct Input { std::u16string text; unsigned role; int width; };
int main(int argc, char** argv) {
  if (argc != 3) return 2;
  dk_engine_t* raw = nullptr;
  check(dk_engine_create_from_file_for_profile_v1(argv[1], DK_PAGE_PROFILE_MADINAH_1405_V1, &raw));
  Engine engine{raw, dk_engine_destroy};
  std::map<int, std::vector<Input>> pages;
  std::ifstream file(argv[2]);
  std::string row;
  while (std::getline(file, row)) {
    std::istringstream fields(row);
    int number, line, width;
    unsigned role;
    std::string units, unit;
    fields >> number >> line >> role >> width >> units;
    if (!fields || line != static_cast<int>(pages[number].size())) return 3;
    std::u16string text;
    std::istringstream hex(units);
    while (std::getline(hex, unit, ',')) text.push_back(static_cast<char16_t>(std::stoul(unit, nullptr, 16)));
    pages[number].push_back({text, width > 0 ? DK_PAGE_LINE_ROLE_ORDINARY : role, width});
  }
  std::cout << std::setprecision(15) << "{\"pages\":[";
  std::set<uint32_t> glyph_ids;
  bool first = true;
  for (const auto& [number, records] : pages) {
    std::vector<dk_page_line_input_v1_t> inputs;
    for (const auto& record : records) inputs.push_back({
        DK_PAGE_LINE_INPUT_V1_SIZE, 0, reinterpret_cast<const uint16_t*>(record.text.data()),
        record.text.size(), record.width, record.role,
        record.width > 0 ? DK_PAGE_ALIGNMENT_DISTRIBUTE : DK_PAGE_ALIGNMENT_CENTER});
    dk_page_options_v1_t options{DK_PAGE_OPTIONS_V1_SIZE, DK_PAGE_PROFILE_MADINAH_1405_V1, 0, 16700, sizeof(inputs[0])};
    dk_page_t* raw_page = nullptr;
    check(dk_engine_shape_page_utf16_v1(engine.get(), &options, inputs.data(), inputs.size(), &raw_page));
    Page page{raw_page, dk_page_destroy};
    if (!first) std::cout << ',';
    first = false;
    std::cout << "{\"number\":" << number << ",\"lines\":[";
    for (size_t i = 0; i < inputs.size(); ++i) {
      dk_page_line_v1_t line{};
      line.struct_size = DK_PAGE_LINE_V1_SIZE;
      check(dk_page_get_line_v1(page.get(), i, &line));
      if (i) std::cout << ',';
      std::cout << "{\"font_scale\":" << line.font_scale << ",\"x_origin\":" << line.x_origin << ",\"final_width\":" << line.final_width << ",\"glyphs\":[";
      double width = 0;
      for (size_t j = 0; j < line.glyph_count; ++j) {
        dk_page_glyph_v1_t glyph{};
        glyph.struct_size = DK_PAGE_GLYPH_V1_SIZE;
        check(dk_page_get_glyph_v1(page.get(), i, j, &glyph));
        if (j) std::cout << ',';
        width += glyph.x_advance;
        glyph_ids.insert(glyph.glyph_id);
        std::cout << '[' << glyph.glyph_id << ',' << glyph.cluster << ',' << glyph.x_advance << ','
                  << glyph.y_advance << ',' << glyph.x_offset << ',' << glyph.y_offset << ']';
      }
      if (std::abs(width - line.final_width) > 0.00001) return 4;
      std::cout << "]}";
    }
    std::cout << "]}";
  }
  std::cout << "],\"outlines\":{";
  first = true;
  for (const auto id : glyph_ids) {
    std::ostringstream path;
    path << std::setprecision(12);
    dk_path_sink_v1_t sink{DK_PATH_SINK_V1_SIZE, &path, move_to, line_to, quadratic_to, cubic_to, close_path};
    dk_glyph_variant_v1_t variant{DK_GLYPH_VARIANT_V1_SIZE, id, 0, 0, 0};
    check(dk_engine_emit_glyph_outline_v1(engine.get(), &variant, &sink));
    if (!first) std::cout << ',';
    first = false;
    std::cout << '"' << id << "\":\"" << path.str() << '"';
  }
  std::cout << "}}\n";
}
