#include "luz/diagnostics.hpp"

// Intentionally empty — ParseError is header-only for now. This .cpp exists so
// CMake has a translation unit to compile and so future diagnostic helpers
// (source-line printing, error-list aggregation, color formatting) have a home.

namespace luz {
}
