// luzc -- native Luz compiler (C++ implementation)
//
// Status: scaffolding. Reuses luz/c_lexer/ for tokenization. Parser currently
// handles expression statements only (literals + arithmetic + calls); the rest
// of the pipeline will be ported from the Python sources module by module.

#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "luz/ast_printer.hpp"
#include "luz/diagnostics.hpp"
#include "luz/lexer.hpp"
#include "luz/parser.hpp"
#include "luz/typechecker.hpp"

namespace {

constexpr const char* kVersion = "0.0.1";

void print_usage() {
    std::cerr <<
        "luzc " << kVersion << "  (C++ scaffold)\n"
        "\n"
        "Usage:\n"
        "  luzc <file.luz>            compile + run (not yet implemented)\n"
        "  luzc <file.luz> --tokens   dump token stream\n"
        "  luzc <file.luz> --ast      dump parsed AST\n"
        "  luzc <file.luz> --check    run type checker and report errors\n"
        "  luzc --version             print version\n"
        "  luzc --help                show this message\n";
}

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::in | std::ios::binary);
    if (!in) {
        throw std::runtime_error("cannot open '" + path + "'");
    }
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

int cmd_tokens(const std::string& source) {
    auto tokens = luz::lex(source);
    for (const auto& t : tokens) {
        std::cout << t.line << ':' << t.col
                  << "  " << luz::token_type_name(t.type);
        if (!t.value.empty()) {
            std::cout << "  \"" << t.value << "\"";
        }
        std::cout << '\n';
    }
    return 0;
}

int cmd_ast(const std::string& source) {
    auto tokens  = luz::lex(source);
    auto program = luz::parse(tokens);
    luz::print_ast(std::cout, program);
    return 0;
}

int cmd_check(const std::string& source, const std::string& file) {
    auto tokens  = luz::lex(source);
    auto program = luz::parse(tokens);
    auto errors  = luz::type_check(program);
    if (errors.empty()) {
        std::cout << "No type errors found.\n";
        return 0;
    }
    for (auto& e : errors) {
        std::cerr << file << ':' << e.line << ':' << e.col
                  << ": " << e.kind << ": " << e.message << '\n';
    }
    return 1;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> args(argv + 1, argv + argc);

    if (args.empty() || args[0] == "--help" || args[0] == "-h") {
        print_usage();
        return args.empty() ? 1 : 0;
    }
    if (args[0] == "--version") {
        std::cout << "luzc " << kVersion << '\n';
        return 0;
    }

    const std::string& file = args[0];
    std::string mode = args.size() >= 2 ? args[1] : "--run";

    try {
        std::string source = read_file(file);

        if (mode == "--tokens") return cmd_tokens(source);
        if (mode == "--ast")    return cmd_ast(source);
        if (mode == "--check")  return cmd_check(source, file);

        std::cerr << "luzc: backend not yet implemented -- try --tokens or --ast\n";
        return 2;
    } catch (const luz::ParseError& e) {
        std::cerr << file << ':' << e.line() << ':' << e.col()
                  << ": error: " << e.what() << '\n';
        return 1;
    } catch (const std::exception& e) {
        std::cerr << "luzc: " << e.what() << '\n';
        return 1;
    }
}
