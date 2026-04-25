// luzc — native Luz compiler

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#ifndef _WIN32
#  include <unistd.h>    // unlink
#endif

#include "luz/ast_printer.hpp"
#include "luz/codegen.hpp"
#include "luz/diagnostics.hpp"
#include "luz/hir.hpp"
#include "luz/lexer.hpp"
#include "luz/parser.hpp"
#include "luz/typechecker.hpp"

#ifndef LUZ_RT_SOURCE
#  define LUZ_RT_SOURCE ""
#endif

namespace {

constexpr const char* kVersion    = "2.0.0-dev";
constexpr const char* kRtSource   = LUZ_RT_SOURCE;

// ── Helpers ───────────────────────────────────────────────────────────────────

void print_usage() {
    std::cerr <<
        "luzc " << kVersion << "\n"
        "\n"
        "Usage:\n"
        "  luzc <file.luz>                    compile to native binary\n"
        "  luzc <file.luz> -o <out>           compile with custom output name\n"
        "  luzc <file.luz> --run              compile + run immediately\n"
        "  luzc <file.luz> --emit-llvm        emit LLVM IR to stdout\n"
        "  luzc <file.luz> --emit-llvm -o f   emit LLVM IR to file\n"
        "  luzc <file.luz> --tokens           dump token stream\n"
        "  luzc <file.luz> --ast              dump parsed AST\n"
        "  luzc <file.luz> --hir              dump lowered HIR\n"
        "  luzc <file.luz> --check            type-check, human-readable\n"
        "  luzc <file.luz> --check-json       type-check, JSON output\n"
        "  luzc --version                     print version\n"
        "  luzc --help                        show this message\n";
}

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::in | std::ios::binary);
    if (!in) throw std::runtime_error("cannot open '" + path + "'");
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

// Return a writable temp file path with the given suffix.
std::string temp_path(const std::string& suffix) {
    char buf[L_tmpnam];
    std::tmpnam(buf);
    return std::string(buf) + suffix;
}

void delete_file(const std::string& path) {
    std::remove(path.c_str());
}

// Run a shell command. Returns the process exit code.
int run_cmd(const std::string& cmd) {
    return std::system(cmd.c_str());
}

// Escape a path for use in a shell command (handles spaces).
std::string shell_quote(const std::string& s) {
#ifdef _WIN32
    return "\"" + s + "\"";
#else
    std::string out = "'";
    for (char c : s) { if (c == '\'') out += "'\\''"; else out += c; }
    return out + "'";
#endif
}

// Derive default output name from source file.
std::string default_output(const std::string& source_file) {
    auto dot = source_file.rfind('.');
    std::string base = (dot != std::string::npos)
                       ? source_file.substr(0, dot)
                       : source_file;
#ifdef _WIN32
    if (base.size() < 4 || base.substr(base.size() - 4) != ".exe")
        base += ".exe";
#endif
    return base;
}

// ── Pipeline stages ───────────────────────────────────────────────────────────

int cmd_tokens(const std::string& source) {
    for (const auto& t : luz::lex(source)) {
        std::cout << t.line << ':' << t.col
                  << "  " << luz::token_type_name(t.type);
        if (!t.value.empty()) std::cout << "  \"" << t.value << "\"";
        std::cout << '\n';
    }
    return 0;
}

int cmd_ast(const std::string& source) {
    luz::print_ast(std::cout, luz::parse(luz::lex(source)));
    return 0;
}

int cmd_hir(const std::string& source) {
    luz::print_hir(std::cout, luz::lower_to_hir(luz::parse(luz::lex(source))));
    return 0;
}

int cmd_emit_llvm(const std::string& source, const std::string& file,
                  const std::string& out_path) {
    auto hir = luz::lower_to_hir(luz::parse(luz::lex(source)));
    if (out_path.empty() || out_path == "-") {
        luz::emit_llvm_ir(std::cout, hir, file);
        return 0;
    }
    std::ofstream of(out_path, std::ios::out | std::ios::binary);
    if (!of) throw std::runtime_error("cannot open '" + out_path + "'");
    luz::emit_llvm_ir(of, hir, file);
    std::cerr << "luzc: wrote LLVM IR to " << out_path << "\n";
    return 0;
}

int cmd_check(const std::string& source, const std::string& file) {
    auto errors = luz::type_check(luz::parse(luz::lex(source)));
    if (errors.empty()) { std::cout << "No type errors found.\n"; return 0; }
    for (auto& e : errors)
        std::cerr << file << ':' << e.line << ':' << e.col
                  << ": " << e.kind << ": " << e.message << '\n';
    return 1;
}

// JSON-formatted check — used by the VS Code extension.
int cmd_check_json(const std::string& source, const std::string& /*file*/) {
    std::vector<luz::TypeCheckError> errors;
    try {
        errors = luz::type_check(luz::parse(luz::lex(source)));
    } catch (const luz::ParseError& e) {
        std::cout << "[{\"line\":" << e.line()
                  << ",\"col\":"   << e.col()
                  << ",\"message\":\"" << e.what() << "\"}]\n";
        return 1;
    }
    std::cout << "[";
    for (int i = 0; i < (int)errors.size(); ++i) {
        if (i) std::cout << ",";
        // Minimal JSON escaping for the message string
        std::string msg;
        for (char c : errors[i].message) {
            if      (c == '"' ) msg += "\\\"";
            else if (c == '\\') msg += "\\\\";
            else if (c == '\n') msg += "\\n";
            else                msg += c;
        }
        std::cout << "{\"line\":" << errors[i].line
                  << ",\"col\":"  << errors[i].col
                  << ",\"message\":\"" << msg << "\"}";
    }
    std::cout << "]\n";
    return errors.empty() ? 0 : 1;
}

// Compile source → LLVM IR → native binary via clang.
// Returns exit code (0 = success).
int cmd_compile(const std::string& source, const std::string& src_file,
                const std::string& output, bool verbose) {
    // 1. Emit LLVM IR to a temp file
    std::string ir_file = temp_path(".ll");
    {
        std::ofstream of(ir_file, std::ios::out | std::ios::binary);
        if (!of) throw std::runtime_error("cannot create temp IR file");
        luz::emit_llvm_ir(of, luz::lower_to_hir(luz::parse(luz::lex(source))),
                          src_file);
    }

    // 2. Build clang command: ir + runtime C source → binary
    std::string rt = kRtSource;
    if (rt.empty()) {
        // Fallback: look for luz_rt.c next to the binary
        rt = "luz_rt.c";
    }

    std::string cmd = "clang -O2 "
                    + shell_quote(ir_file) + " "
                    + shell_quote(rt)      + " "
                    + "-o " + shell_quote(output);

    if (verbose) std::cerr << "luzc: " << cmd << "\n";

    int rc = run_cmd(cmd);
    delete_file(ir_file);

    if (rc != 0) {
        std::cerr << "luzc: clang failed (exit " << rc << ")\n"
                  << "      Make sure clang is in PATH.\n";
        return 1;
    }

    if (verbose)
        std::cerr << "luzc: compiled -> " << output << "\n";
    else
        std::cout << "Compiled: " << output << "\n";

    return 0;
}

int cmd_run(const std::string& source, const std::string& src_file) {
    std::string tmp_bin = temp_path(
#ifdef _WIN32
        ".exe"
#else
        ""
#endif
    );

    int rc = cmd_compile(source, src_file, tmp_bin, /*verbose=*/false);
    if (rc != 0) return rc;

    // Execute
    std::string run_cmd_str = shell_quote(tmp_bin);
    rc = run_cmd(run_cmd_str);

    delete_file(tmp_bin);
    return rc;
}

}  // namespace

// ── Entry point ───────────────────────────────────────────────────────────────

int main(int argc, char** argv) {
    std::vector<std::string> args(argv + 1, argv + argc);

    if (args.empty() || args[0] == "--help" || args[0] == "-h") {
        print_usage();
        return args.empty() ? 1 : 0;
    }
    if (args[0] == "--version" || args[0] == "-v") {
        std::cout << "luzc " << kVersion << '\n';
        return 0;
    }

    const std::string& file = args[0];

    // Parse flags
    std::string mode;
    std::string output;
    bool verbose = false;

    for (int i = 1; i < (int)args.size(); ++i) {
        const std::string& a = args[i];
        if (a == "-o" && i + 1 < (int)args.size()) {
            output = args[++i];
        } else if (a == "-v" || a == "--verbose") {
            verbose = true;
        } else if (!a.empty() && a[0] == '-') {
            mode = a;
        }
    }

    try {
        std::string source = read_file(file);

        if (mode == "--tokens")     return cmd_tokens(source);
        if (mode == "--ast")        return cmd_ast(source);
        if (mode == "--hir")        return cmd_hir(source);
        if (mode == "--check")      return cmd_check(source, file);
        if (mode == "--check-json") return cmd_check_json(source, file);
        if (mode == "--emit-llvm")  return cmd_emit_llvm(source, file, output);
        if (mode == "--run")        return cmd_run(source, file);

        // Default: compile to binary
        if (output.empty()) output = default_output(file);
        return cmd_compile(source, file, output, verbose);

    } catch (const luz::ParseError& e) {
        std::cerr << file << ':' << e.line() << ':' << e.col()
                  << ": error: " << e.what() << '\n';
        return 1;
    } catch (const std::exception& e) {
        std::cerr << "luzc: " << e.what() << '\n';
        return 1;
    }
}
