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
#include "luz/codegen.hpp"
#include "luz/diagnostics.hpp"
#include "luz/hir.hpp"
#include "luz/lexer.hpp"
#include "luz/parser.hpp"
#include "luz/typechecker.hpp"

namespace {

constexpr const char* kVersion = "0.0.1";

void print_usage() {
    std::cerr <<
        "luzc " << kVersion << "\n"
        "\n"
        "Usage:\n"
        "  luzc <file.luz> --emit-llvm           emit LLVM IR to stdout\n"
        "  luzc <file.luz> --emit-llvm -o out.ll write LLVM IR to file\n"
        "  luzc <file.luz> --tokens              dump token stream\n"
        "  luzc <file.luz> --ast                 dump parsed AST\n"
        "  luzc <file.luz> --check               run type checker\n"
        "  luzc <file.luz> --hir                 dump lowered HIR\n"
        "  luzc --version                        print version\n"
        "  luzc --help                           show this message\n"
        "\n"
        "To compile and run:\n"
        "  luzc prog.luz --emit-llvm -o prog.ll\n"
        "  clang prog.ll -o prog && ./prog\n";
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

int cmd_hir(const std::string& source) {
    auto tokens  = luz::lex(source);
    auto program = luz::parse(tokens);
    auto hir     = luz::lower_to_hir(program);
    luz::print_hir(std::cout, hir);
    return 0;
}

int cmd_emit_llvm(const std::string& source, const std::string& file,
                  const std::string& out_path) {
    auto tokens  = luz::lex(source);
    auto program = luz::parse(tokens);
    if (out_path.empty() || out_path == "-") {
        luz::emit_llvm_ir(std::cout, luz::lower_to_hir(program), file);
        return 0;
    }
    std::ofstream of(out_path, std::ios::out | std::ios::binary);
    if (!of) throw std::runtime_error("cannot open output file '" + out_path + "'");
    luz::emit_llvm_ir(of, luz::lower_to_hir(program), file);
    std::cerr << "luzc: wrote LLVM IR to " << out_path << "\n";
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
    std::string mode = args.size() >= 2 ? args[1] : "--emit-llvm";

    try {
        std::string source = read_file(file);

        if (mode == "--tokens") return cmd_tokens(source);
        if (mode == "--ast")    return cmd_ast(source);
        if (mode == "--hir")    return cmd_hir(source);
        if (mode == "--check")  return cmd_check(source, file);
        if (mode == "--emit-llvm") {
            // optional: --emit-llvm -o <file>
            std::string out_path;
            if (args.size() >= 4 && args[2] == "-o") out_path = args[3];
            return cmd_emit_llvm(source, file, out_path);
        }

        std::cerr << "luzc: unknown mode '" << mode << "' -- try --help\n";
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
