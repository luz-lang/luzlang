cmake_minimum_required(VERSION 3.16)

add_executable(luz_tests
    test_main.cpp
    test_lexer.cpp
    test_parser.cpp
    test_typechecker.cpp
    test_hir.cpp
)

target_include_directories(luz_tests PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../include
)

target_link_libraries(luz_tests PRIVATE luz_c_lexer)

# Re-compile the compiler sources into the test binary.
target_sources(luz_tests PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/lexer.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/parser.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/ast_printer.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/diagnostics.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/typechecker.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/hir.cpp
)

include(CTest)
add_test(NAME luz_tests COMMAND luz_tests)
