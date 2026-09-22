cmake_minimum_required(VERSION 3.24)
project(digitalkhatt_consumer LANGUAGES C CXX)

find_package(engine REQUIRED CONFIG)
add_library(digitalkhatt_consumer SHARED consumer.cpp)
target_link_libraries(digitalkhatt_consumer PRIVATE engine::digitalkhatt)
