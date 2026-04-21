#pragma once

#include <string>
#include <vector>

#include "luz/token.hpp"

namespace luz {

// Run the C lexer on `source` and return an owning vector of tokens.
// The final token is always of type TT_EOF.
// Throws std::runtime_error on allocation failure from the C side.
std::vector<Token> lex(const std::string& source);

}  // namespace luz
