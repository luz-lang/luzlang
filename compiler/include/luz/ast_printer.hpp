#pragma once

#include <ostream>

#include "luz/ast.hpp"

namespace luz {

void print_ast(std::ostream& os, const Program& program);

}  // namespace luz
