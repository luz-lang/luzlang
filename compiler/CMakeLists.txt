cmake_minimum_required(VERSION 3.16)
project(luzc CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Debug)
endif()

if(MSVC)
    add_compile_options(/W4 /permissive-)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Reuse the existing C lexer from luz/c_lexer/ instead of porting it.
# It already produces the same token stream the Python pipeline consumes.
set(LUZ_C_LEXER_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../luz/c_lexer)

add_library(luz_c_lexer STATIC
    ${LUZ_C_LEXER_DIR}/luz_lexer.c
)
target_include_directories(luz_c_lexer PUBLIC ${LUZ_C_LEXER_DIR})

add_library(luz_rt STATIC
    runtime/luz_rt.c
)

add_executable(luzc
    src/main.cpp
    src/lexer.cpp
    src/parser.cpp
    src/ast_printer.cpp
    src/diagnostics.cpp
    src/typechecker.cpp
    src/hir.cpp
    src/codegen.cpp
)

target_include_directories(luzc PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(luzc PRIVATE luz_c_lexer luz_rt)

enable_testing()
# Tests will be wired up once a first module lands (see tests/CMakeLists.txt).
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/tests/CMakeLists.txt)
    add_subdirectory(tests)
endif()
