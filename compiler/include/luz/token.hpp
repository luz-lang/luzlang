#pragma once

#include <cstdint>
#include <string>

extern "C" {
#include "luz_lexer.h"
}

namespace luz {

// C++ view of a CToken. Owns its string value so the C-side buffer can be freed
// immediately after the scan, and the parser can work with std::string.
struct Token {
    TokenType   type  = TT_EOF;
    std::string value;
    int         line  = 0;
    int         col   = 0;

    bool is(TokenType t) const noexcept { return type == t; }
};

const char* token_type_name(TokenType t) noexcept;

}  // namespace luz
