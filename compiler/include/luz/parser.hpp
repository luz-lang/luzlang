#pragma once

#include <vector>

#include "luz/ast.hpp"
#include "luz/token.hpp"

namespace luz {

// Parse a token stream into a Program. Throws ParseError on malformed input.
//
// Scope of this first iteration: expression statements only — literals,
// identifiers, arithmetic with correct precedence, and function calls. Enough
// to parse programs like `write(5 + 5)`. Statements (let, if, while, etc.)
// are added in later passes.
Program parse(const std::vector<Token>& tokens);

}  // namespace luz
