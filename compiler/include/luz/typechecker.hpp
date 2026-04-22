#pragma once

#include <string>
#include <vector>

#include "luz/ast.hpp"

namespace luz {

struct TypeCheckError {
    std::string message;
    int         line = 0;
    int         col  = 0;
    std::string kind = "TypeCheckFault";
};

// Walk the AST, infer types, and return all detected errors.
// Collects all errors rather than stopping at the first.
std::vector<TypeCheckError> type_check(const Program& program);

}  // namespace luz
