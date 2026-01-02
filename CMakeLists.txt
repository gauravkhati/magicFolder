cmake_minimum_required(VERSION 3.16)
project(MagicFolder VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Find required packages
find_package(PkgConfig REQUIRED)
pkg_check_modules(FUSE3 REQUIRED fuse3)
pkg_check_modules(ZMQ REQUIRED libzmq)

# Main executable
add_executable(magic_folder
    src/magic_folder.cpp
)

# Include directories
target_include_directories(magic_folder PRIVATE
    ${FUSE3_INCLUDE_DIRS}
    ${ZMQ_INCLUDE_DIRS}
)

# Link directories
target_link_directories(magic_folder PRIVATE
    ${ZMQ_LIBRARY_DIRS}
)

# Link libraries
target_link_libraries(magic_folder PRIVATE
    ${FUSE3_LIBRARIES}
    ${ZMQ_LIBRARIES}
)

# Compiler flags
target_compile_options(magic_folder PRIVATE
    ${FUSE3_CFLAGS_OTHER}
    ${ZMQ_CFLAGS_OTHER}
    -Wall
    -Wextra
    -Wpedantic
)

# Installation
install(TARGETS magic_folder
    RUNTIME DESTINATION bin
)

# Print configuration summary
message(STATUS "")
message(STATUS "MagicFolder Configuration:")
message(STATUS "  FUSE3 version: ${FUSE3_VERSION}")
message(STATUS "  FUSE3 include: ${FUSE3_INCLUDE_DIRS}")
message(STATUS "  FUSE3 libs: ${FUSE3_LIBRARIES}")
message(STATUS "")
