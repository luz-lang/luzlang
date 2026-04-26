#pragma once

// ccodegen.hpp — C source emitter for the Luz compiler.
//
// Produces a self-contained .c file from a HIR program.
// Compile the output with TCC (bundled) or any C99 compiler:
//   tcc output.c luz_rt.c -o output

#include <iosfwd>
#include <string>

#include "luz/hir.hpp"

namespace luz {

void emit_c(std::ostream& out,
            const HirBlock& program,
            const std::string& filename = "program.luz");

}  // namespace luz
