# Base Error Class
class LuzError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)

# Internal signals for control flow (not faults)
class ReturnException(LuzError):
    def __init__(self, value):
        self.value = value
        super().__init__("Return signal")

class BreakException(LuzError):
    def __init__(self): super().__init__("Break signal")

class ContinueException(LuzError):
    def __init__(self): super().__init__("Continue signal")

# --- 1. Syntax & Parsing Faults ---
class SyntaxFault(LuzError): pass
class ParseFault(SyntaxFault): pass
class ExpressionFault(SyntaxFault): pass
class OperatorFault(SyntaxFault): pass
class UnexpectedTokenFault(SyntaxFault): pass
class InvalidTokenFault(SyntaxFault): pass
class StructureFault(SyntaxFault): pass
class UnexpectedEOFault(SyntaxFault): pass

# --- 2. Semantic Faults ---
class SemanticFault(LuzError): pass
# Data Types
class TypeClashFault(SemanticFault): pass
class TypeViolationFault(SemanticFault): pass
class CastFault(SemanticFault): pass
# Variables & Environment
class UndefinedSymbolFault(SemanticFault): pass
class DuplicateSymbolFault(SemanticFault): pass
class ScopeFault(SemanticFault): pass
# Functions
class FunctionNotFoundFault(SemanticFault): pass
class ArgumentFault(SemanticFault): pass
class ArityFault(SemanticFault): pass
class InvalidUsageFault(SemanticFault): pass
# Control Flow
class FlowControlFault(SemanticFault): pass
class ReturnFault(SemanticFault): pass
class LoopFault(SemanticFault): pass

# --- 3. Runtime Faults ---
class RuntimeFault(LuzError): pass
class ExecutionFault(RuntimeFault): pass
class InternalFault(RuntimeFault): pass
class IllegalOperationFault(RuntimeFault): pass
# Mathematical
class NumericFault(RuntimeFault): pass
class ZeroDivisionFault(NumericFault): pass
class OverflowFault(NumericFault): pass
# Memory & Structures
class MemoryAccessFault(RuntimeFault): pass
class IndexFault(RuntimeFault): pass

# --- 4. System & Modules ---
class ModuleNotFoundFault(LuzError): pass
class ImportFault(LuzError): pass
class UserFault(LuzError): pass # For 'alert'
