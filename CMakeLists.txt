cmake_minimum_required(VERSION 3.18)
project(TestHPX)

find_package(HPX CONFIG REQUIRED)

add_executable(test_hpx main.cpp)
target_link_libraries(test_hpx PRIVATE HPX::hpx)
