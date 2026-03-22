# tokens.py
#
# This module defines the fundamental building blocks that the lexer produces and
# the parser consumes: the TokenType enumeration and the Token data class.
#
# Role in the pipeline:
#   Source text → [Lexer] → list of Tokens → [Parser] → AST → [Interpreter] → result
#
# Every other module imports from here, so this file has no dependencies on the
# rest of the Luz codebase — it is the foundation of the whole stack.

from enum import Enum, auto


# TokenType enumerates every distinct kind of symbol that can appear in a Luz
# program.  Using an Enum (rather than plain string constants) means that
# comparisons are identity checks at the C level inside CPython — fast and
# typo-proof, since a misspelled name raises AttributeError immediately.
#
# auto() assigns a unique integer to each member automatically, so we never
# have to manage raw values ourselves.  The actual integer doesn't matter; only
# the identity of the enum member is used throughout the codebase.
class TokenType(Enum):
    # ── Numeric literals ─────────────────────────────────────────────────────
    INT = auto()       # Whole-number literal, e.g. 42
    FLOAT = auto()     # Decimal literal, e.g. 3.14

    # ── Arithmetic operators ──────────────────────────────────────────────────
    PLUS = auto()      # +
    MINUS = auto()     # -  (also used as unary negation)
    MUL = auto()       # *
    DIV = auto()       # /  (always produces a float result)
    MOD = auto()       # %  (modulo / remainder)
    POW = auto()       # ** (exponentiation; right-associative)
    IDIV = auto()      # // (integer / floor division)

    # ── Grouping ──────────────────────────────────────────────────────────────
    LPAREN = auto()    # (
    RPAREN = auto()    # )

    # ── Identifiers & assignment ──────────────────────────────────────────────
    IDENTIFIER = auto()  # Any user-defined name (variable, function, …)
    ASSIGN = auto()      # =  (assignment; NOT equality — that is EE)

    # ── Comparison / relational operators ────────────────────────────────────
    EE = auto()        # ==  (equality)
    NE = auto()        # !=  (inequality)
    LT = auto()        # <
    GT = auto()        # >
    LTE = auto()       # <=
    GTE = auto()       # >=

    # ── Control-flow keywords ─────────────────────────────────────────────────
    IF = auto()
    ELIF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    TO = auto()        # Used in for-range syntax:  for i = 0 to 10 { … }
    IN = auto()        # Used in for-each syntax:   for item in list { … }

    # ── Boolean literals ──────────────────────────────────────────────────────
    TRUE = auto()
    FALSE = auto()
    NULL = auto()      # null — the absence of a value

    # ── Logical operators ─────────────────────────────────────────────────────
    AND = auto()
    OR = auto()
    NOT = auto()       # Unary logical negation

    # ── Functions & scope ────────────────────────────────────────────────────
    FUNCTION = auto()  # Keyword that begins a function definition
    RETURN = auto()    # Return a value from a function
    FN = auto()        # fn — short keyword for lambdas / anonymous functions
    ARROW = auto()     # => — separates params from body in a lambda

    # ── Module system ────────────────────────────────────────────────────────
    IMPORT = auto()    # Import another Luz source file into the global env

    # ── Error handling ───────────────────────────────────────────────────────
    ATTEMPT = auto()   # attempt { … }  (analogous to try)
    RESCUE = auto()    # rescue (e) { … }  (analogous to except/catch)
    ALERT = auto()     # alert <expr>  — raise a user-defined error

    # ── Loop control ─────────────────────────────────────────────────────────
    BREAK = auto()
    CONTINUE = auto()
    PASS = auto()      # No-op placeholder (like Python's pass)

    # ── Object-oriented programming ───────────────────────────────────────────
    CLASS = auto()     # class keyword - begins a class definition
    SELF = auto()      # self - refers to the current instance
    EXTENDS = auto()   # extends - declares the parent class:  class Dog extends Animal
    DOT = auto()       # .  - attribute access: obj.name


    # ── String literals ───────────────────────────────────────────────────────
    STRING = auto()    # Double-quoted string, e.g. "hello"
    FSTRING = auto()   # Format string, e.g. $"Hello {name}"  (expressions in {})

    # ── Punctuation / delimiters ──────────────────────────────────────────────
    COMMA = auto()     # ,  (argument separators, list elements, …)
    COLON = auto()     # :  (dictionary key-value separator)
    LBRACKET = auto()  # [  (list literals and index access)
    RBRACKET = auto()  # ]
    LBRACE = auto()    # {  (block delimiter for every compound statement)
    RBRACE = auto()    # }

    # ── Compound assignment ───────────────────────────────────────────────────
    PLUS_ASSIGN  = auto()  # +=
    MINUS_ASSIGN = auto()  # -=
    MUL_ASSIGN   = auto()  # *=
    DIV_ASSIGN   = auto()  # /=

    # ── Variadic ──────────────────────────────────────────────────────────────
    ELLIPSIS = auto()  # ... — marks a variadic parameter: function f(...args)

    # ── Switch / Match ────────────────────────────────────────────────────────
    SWITCH = auto()    # switch <expr> { case … }
    CASE   = auto()    # case <expr>, … { block }
    MATCH  = auto()    # match <expr> { pattern => expr, … }

    # ── Sentinel ─────────────────────────────────────────────────────────────
    EOF = auto()       # End-of-file marker; always the last token in the list


# Token is the value object that travels from the lexer to the parser.
# It carries three pieces of information:
#   • type  – which TokenType member this token is
#   • value – the "payload" (the actual number, string text, or identifier
#              name).  Operator/keyword tokens have value=None because the
#              type alone fully describes them.
#   • line  – the source line where the token appeared, used to attach
#              meaningful line numbers to error messages later in the pipeline.
class Token:
    def __init__(self, type, value=None, line=None):
        self.type = type
        self.value = value
        self.line = line

    # __repr__ is used when printing token lists during debugging.
    # "INT:42" is more readable than the default object address.
    def __repr__(self):
        if self.value is not None:
            return f"{self.type.name}:{self.value}"
        return f"{self.type.name}"
