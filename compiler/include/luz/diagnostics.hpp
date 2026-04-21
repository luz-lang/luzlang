#pragma once

#include <stdexcept>
#include <string>

namespace luz {

// Thrown on any parse/lex error. Carries 1-based source position so the CLI
// can print GCC-style error messages. Kept deliberately simple — the full
// multi-diagnostic reporter from luzc.py will be ported later.
class ParseError : public std::runtime_error {
public:
    ParseError(std::string msg, int line, int col)
        : std::runtime_error(std::move(msg)), line_(line), col_(col) {}

    int line() const noexcept { return line_; }
    int col()  const noexcept { return col_;  }

private:
    int line_;
    int col_;
};

}  // namespace luz
