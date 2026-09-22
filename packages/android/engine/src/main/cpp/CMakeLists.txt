cmake_minimum_required(VERSION 3.24)
project(digitalkhatt_android LANGUAGES C CXX)

set(BUILD_SHARED_LIBS OFF)
set(DIGITALKHATT_ENGINE_BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory(
  "${DIGITALKHATT_SOURCE_DIR}/lib/digitalkhatt/runtime"
  "${CMAKE_CURRENT_BINARY_DIR}/digitalkhatt-runtime"
)

add_library(digitalkhatt SHARED empty.cpp)
target_compile_features(digitalkhatt PRIVATE cxx_std_20)
target_link_libraries(
  digitalkhatt PRIVATE "$<LINK_LIBRARY:WHOLE_ARCHIVE,digitalkhatt_engine>"
)
target_link_options(digitalkhatt PRIVATE
  "LINKER:--version-script=${DIGITALKHATT_SOURCE_DIR}/lib/digitalkhatt/runtime/exports.map"
  "LINKER:-z,max-page-size=16384"
)
set_target_properties(digitalkhatt PROPERTIES
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON
)
