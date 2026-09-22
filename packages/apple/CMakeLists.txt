cmake_minimum_required(VERSION 3.24)
project(digitalkhatt_apple LANGUAGES C CXX)

set(BUILD_SHARED_LIBS OFF)
set(DIGITALKHATT_ENGINE_BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory(
  "${DIGITALKHATT_SOURCE_DIR}/lib/digitalkhatt/runtime"
  "${CMAKE_CURRENT_BINARY_DIR}/digitalkhatt-runtime"
)

set(merged "${CMAKE_CURRENT_BINARY_DIR}/libdigitalkhatt_engine_merged.a")
add_custom_command(
  OUTPUT "${merged}"
  COMMAND /usr/bin/libtool -static -D -o "${merged}"
    $<TARGET_FILE:digitalkhatt_engine>
    $<TARGET_FILE:digitalkhatt_engine_core>
    $<TARGET_FILE:digitalkhatt_engine_justify>
    $<TARGET_FILE:harfbuzz>
    $<TARGET_FILE:pcre2-16-static>
  DEPENDS
    digitalkhatt_engine digitalkhatt_engine_core digitalkhatt_engine_justify
    harfbuzz pcre2-16-static
  VERBATIM
)
add_custom_target(digitalkhatt_merged ALL DEPENDS "${merged}")
