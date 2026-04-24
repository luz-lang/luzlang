#pragma once

// codegen.hpp — LLVM IR text emitter for the Luz compiler.
//
// Produces a .ll file (LLVM IR text) from a lowered HIR program.
// No LLVM C++ API required — the output can be compiled with:
//   clang output.ll -o output
//
// Supported Luz types → LLVM IR types:
//   int    → i64
//   float  → double
//   bool   → i1
//   string → i8*  (pointer to a global constant)
//   void   → void

#include <iosfwd>
#include <string>

#include "luz/hir.hpp"

namespace luz {

// Emit LLVM IR text for `program` into `out`.
// `filename` is embedded in the module comment (cosmetic only).
void emit_llvm_ir(std::ostream& out,
                  const HirBlock& program,
                  const std::string& filename = "program.luz");

}  // namespace luz
