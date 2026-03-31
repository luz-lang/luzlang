# exceptions.py
#
# This module defines every exception type used throughout the Luz interpreter.
# Having a dedicated hierarchy (rather than using bare Python exceptions) gives
# several advantages:
#   1. The interpreter's visit() method can catch LuzError specifically and
#      attach line-number information before re-raising, without accidentally
#      swallowing unrelated Python errors.
#   2. Error categories are explicit: callers can catch SemanticFault without
#      needing to know about every individual subclass.
#   3. The rescue (try/catch) mechanism in Luz only intercepts LuzError
#      subclasses, which prevents the interpreter from accidentally hiding its
#      own internal bugs as user-catchable errors.
#
# The hierarchy at a glance:
#
#   LuzError
#   ├── ReturnException        ← control flow (not a real error)
#   ├── BreakException         ← control flow
#   ├── ContinueException      ← control flow
#   ├── SyntaxFault
#   │   ├── ParseFault
#   │   ├── ExpressionFault
#   │   ├── OperatorFault
#   │   ├── UnexpectedTokenFault
#   │   ├── InvalidTokenFault
#   │   ├── StructureFault
#   │   └── UnexpectedEOFault
#   ├── SemanticFault
#   │   ├── TypeClashFault / TypeViolationFault / CastFault
#   │   ├── UndefinedSymbolFault / DuplicateSymbolFault / ScopeFault
#   │   ├── FunctionNotFoundFault / ArgumentFault / ArityFault / InvalidUsageFault
#   │   └── FlowControlFault / ReturnFault / LoopFault
#   ├── RuntimeFault
#   │   ├── ExecutionFault / InternalFault / IllegalOperationFault
#   │   ├── NumericFault → ZeroDivisionFault / OverflowFault
#   │   └── MemoryAccessFault / IndexFault
#   ├── ModuleNotFoundFault
#   ├── ImportFault
#   └── UserFault              ← raised by the `alert` keyword


# ── Base ──────────────────────────────────────────────────────────────────────

# All Luz exceptions inherit from LuzError so that a single `except LuzError`
# can catch anything the language itself can raise.  The `line` attribute is
# initialised to None here and filled in by the interpreter's visit() method
# once the executing node's source line is known.
class LuzError(Exception):
    def __init__(self, message):
        self.message = message
        self.line = None   # Populated by the interpreter before the error propagates
        self.col = None
        super().__init__(message)


# ── Control-flow signals ──────────────────────────────────────────────────────
# These three classes are technically subclasses of LuzError for convenience
# (so they travel through the same raise/catch infrastructure), but they are
# NOT errors — they are signals that unwind the call stack to implement
# `return`, `break`, and `continue`.
#
# Why exceptions for control flow?
#   Because Python's own call stack mirrors the recursive-descent interpreter's
#   call stack, there is no clean way to exit multiple nested visit() frames
#   without raising.  This pattern is common in tree-walking interpreters.
#
# The interpreter's central visit() method specifically excludes these three
# from receiving line-number decoration, and the Luz `rescue` block is also
# forbidden from catching them (they are re-raised immediately).

class ReturnException(LuzError):
    # Carries the return value up through execute_block / visit_FuncDefNode
    # until LuzFunction.__call__ catches it.
    def __init__(self, value):
        self.value = value
        super().__init__("Return signal")

class BreakException(LuzError):
    # Caught by visit_WhileNode and visit_ForNode to exit a loop early.
    def __init__(self): super().__init__("Break signal")

class ContinueException(LuzError):
    # Caught by visit_WhileNode and visit_ForNode to skip to the next iteration.
    def __init__(self): super().__init__("Continue signal")


# ── 1. Syntax & Parsing Faults ────────────────────────────────────────────────
# These are raised during the lexing and parsing phases, before any code runs.
# They indicate that the source text does not conform to Luz grammar.

class SyntaxFault(LuzError): pass

# Raised as a catch-all when an unexpected error occurs during parsing.
class ParseFault(SyntaxFault): pass

# Raised when the parser cannot start a valid expression at the current token.
class ExpressionFault(SyntaxFault): pass

# Raised when a binary operator has no valid right-hand operand.
class OperatorFault(SyntaxFault): pass

# Raised when the parser finds a token that cannot legally appear at that point.
class UnexpectedTokenFault(SyntaxFault): pass

# Raised by the lexer for unrecognised characters or malformed tokens
# (e.g. an unterminated string or an unknown escape sequence).
class InvalidTokenFault(SyntaxFault): pass

# Raised when a required structural token (e.g. `{` or `:`) is missing.
class StructureFault(SyntaxFault): pass

# Raised when the token stream ends in the middle of a construct that requires
# more tokens (e.g. an unclosed function body).
class UnexpectedEOFault(SyntaxFault): pass


# ── 2. Semantic Faults ────────────────────────────────────────────────────────
# Raised during interpretation when the program is grammatically valid but
# violates the language's type rules, scoping rules, or other semantic constraints.

class SemanticFault(LuzError): pass

# Data-type errors
class TypeClashFault(SemanticFault): pass      # Incompatible types in an operation (e.g. "a" - 1)
class TypeViolationFault(SemanticFault): pass  # Wrong type passed where a specific type is required
class CastFault(SemanticFault): pass           # Explicit cast (to_num, to_int, …) fails on the value

# Variable / environment errors
class UndefinedSymbolFault(SemanticFault): pass   # Reading a variable that was never defined
class DuplicateSymbolFault(SemanticFault): pass   # Defining the same name twice (reserved, not yet used)
class ScopeFault(SemanticFault): pass             # General scope violation

# Function-call errors
class FunctionNotFoundFault(SemanticFault): pass  # Calling a name that doesn't exist as a function
class ArgumentFault(SemanticFault): pass          # Wrong type of argument passed to a builtin
class ArityFault(SemanticFault): pass             # Wrong number of arguments passed to a function
class InvalidUsageFault(SemanticFault): pass      # Using a value in a way it doesn't support
class AttributeNotFoundFault(SemanticFault): pass  # Accessing an attribute that doesn't exist on an instance
class InheritanceFault(SemanticFault): pass        # Invalid inheritance (e.g. circular inheritance chain)

# Control-flow semantic errors (e.g. `break` outside a loop — not yet enforced
# at parse time, so these exist for potential runtime enforcement)
class FlowControlFault(SemanticFault): pass
class ReturnFault(SemanticFault): pass
class LoopFault(SemanticFault): pass

# Raised by the type checker pass (compile-time type analysis).
# Distinct from TypeViolationFault (runtime) so callers can tell them apart.
class TypeCheckFault(SemanticFault): pass

# Raised when a variable, parameter, or import is declared but never read.
# Mirrors Go's "declared and not used" / "imported and not used" rules.
class UnusedVariableFault(SemanticFault): pass
class UnusedImportFault(SemanticFault): pass


# ── 3. Runtime Faults ─────────────────────────────────────────────────────────
# Raised during execution for conditions that only become apparent at runtime.

class RuntimeFault(LuzError): pass
class ExecutionFault(RuntimeFault): pass       # General execution failure
class InternalFault(RuntimeFault): pass        # Bug inside the interpreter itself (should not happen normally)
class IllegalOperationFault(RuntimeFault): pass  # Operation is syntactically valid but semantically illegal

# Mathematical errors
class NumericFault(RuntimeFault): pass
class ZeroDivisionFault(NumericFault): pass    # Division or modulo by zero
class OverflowFault(NumericFault): pass        # Numeric result too large (reserved for future use)

# Collection / memory errors
class MemoryAccessFault(RuntimeFault): pass    # Accessing a dict key that does not exist
class IndexFault(RuntimeFault): pass           # List or string index out of range


# ── 4. System & Module Faults ─────────────────────────────────────────────────
# These sit directly under LuzError rather than under RuntimeFault because they
# occur at the boundary between the interpreter and the host OS/file system.

class ModuleNotFoundFault(LuzError): pass  # `import "path"` where the file doesn't exist
class ImportFault(LuzError): pass          # Any other error while loading/running an imported module
class UserFault(LuzError): pass            # Raised by the `alert` keyword — a deliberate user error
