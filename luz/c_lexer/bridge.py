# luz/c_lexer/bridge.py
#
# Python <-> C bridge for the Luz lexer.
#
# Role in the pipeline:
#   Source text (str) -> [tokenize()] -> calls C lex_all() -> CToken[]
#                     -> converts each CToken -> Token[] (Python)
#
# The bridge has two public functions:
#   available() -> bool   — True if the shared library loaded successfully.
#   tokenize(source) -> list[Token]  — runs the C lexer, returns Python tokens.
#
# The library must be built first:
#   cd luz/c_lexer && make
# Without the .dll / .so the bridge falls back gracefully: available() returns
# False and tokenize() raises RuntimeError so the caller can use the Python lexer.

import ctypes
import os
import sys

from ..tokens import Token, TokenType
from ..exceptions import InvalidTokenFault


# ── Library loading ───────────────────────────────────────────────────────────
# The shared library is expected next to this file in the c_lexer/ directory.

_DIR      = os.path.dirname(__file__)
_LIB_NAME = 'luz_lexer.dll' if sys.platform == 'win32' else 'luz_lexer.so'
_LIB_PATH = os.path.join(_DIR, _LIB_NAME)

try:
    _lib = ctypes.CDLL(_LIB_PATH)
except OSError:
    _lib = None


# ── C struct mirrors ──────────────────────────────────────────────────────────
# Each field list must match the struct layout in luz_lexer.h exactly —
# field order, types, and sizes all matter because ctypes reads raw memory.

class _CLexer(ctypes.Structure):
    # Mirrors:  typedef struct { const char* source; int pos, line, col, length; } CLexer;
    _fields_ = [
        ('source', ctypes.c_char_p),  # pointer — not owned by the lexer
        ('pos',    ctypes.c_int),
        ('line',   ctypes.c_int),
        ('col',    ctypes.c_int),
        ('length', ctypes.c_int),
    ]


class _CToken(ctypes.Structure):
    # Mirrors:  typedef struct { TokenType type; char* value; int line, col; } CToken;
    _fields_ = [
        ('type',  ctypes.c_int),      # enum value (int-sized on all platforms)
        ('value', ctypes.c_char_p),   # heap string or NULL
        ('line',  ctypes.c_int),
        ('col',   ctypes.c_int),
    ]


# ── Function signatures ───────────────────────────────────────────────────────
# Telling ctypes the exact argument and return types prevents silent bugs from
# incorrect implicit conversions (e.g. 64-bit pointer truncated to 32-bit int).

if _lib is not None:
    _lib.lexer_init.restype  = None
    _lib.lexer_init.argtypes = [ctypes.POINTER(_CLexer), ctypes.c_char_p]

    _lib.lex_all.restype  = ctypes.POINTER(_CToken)
    _lib.lex_all.argtypes = [ctypes.POINTER(_CLexer), ctypes.POINTER(ctypes.c_int)]

    _lib.free_tokens.restype  = None
    _lib.free_tokens.argtypes = [ctypes.POINTER(_CToken), ctypes.c_int]


# ── TokenType mapping ─────────────────────────────────────────────────────────
# Maps each C enum integer (its position in the typedef enum) to the matching
# Python TokenType.  The order must follow the typedef enum in luz_lexer.h
# exactly — the numeric values are not stored anywhere, only the positions.
#
# TT_EOF is the last entry.  TT_ERROR sits one slot past the list and is
# handled explicitly below (it raises an exception, never becomes a Token).

_C_TO_PYTHON = [
    TokenType.INT,           #  0  TT_INT
    TokenType.FLOAT,         #  1  TT_FLOAT
    TokenType.PLUS,          #  2  TT_PLUS
    TokenType.MINUS,         #  3  TT_MINUS
    TokenType.MUL,           #  4  TT_MUL
    TokenType.DIV,           #  5  TT_DIV
    TokenType.MOD,           #  6  TT_MOD
    TokenType.POW,           #  7  TT_POW
    TokenType.IDIV,          #  8  TT_IDIV
    TokenType.LPAREN,        #  9  TT_LPAREN
    TokenType.RPAREN,        # 10  TT_RPAREN
    TokenType.IDENTIFIER,    # 11  TT_IDENTIFIER
    TokenType.ASSIGN,        # 12  TT_ASSIGN
    TokenType.EE,            # 13  TT_EE
    TokenType.NE,            # 14  TT_NE
    TokenType.LT,            # 15  TT_LT
    TokenType.GT,            # 16  TT_GT
    TokenType.LTE,           # 17  TT_LTE
    TokenType.GTE,           # 18  TT_GTE
    TokenType.IF,            # 19  TT_IF
    TokenType.ELIF,          # 20  TT_ELIF
    TokenType.ELSE,          # 21  TT_ELSE
    TokenType.WHILE,         # 22  TT_WHILE
    TokenType.FOR,           # 23  TT_FOR
    TokenType.TO,            # 24  TT_TO
    TokenType.IN,            # 25  TT_IN
    TokenType.TRUE,          # 26  TT_TRUE
    TokenType.FALSE,         # 27  TT_FALSE
    TokenType.NULL,          # 28  TT_NULL
    TokenType.AND,           # 29  TT_AND
    TokenType.OR,            # 30  TT_OR
    TokenType.NOT,           # 31  TT_NOT
    TokenType.FUNCTION,      # 32  TT_FUNCTION
    TokenType.RETURN,        # 33  TT_RETURN
    TokenType.FN,            # 34  TT_FN
    TokenType.ARROW,         # 35  TT_ARROW
    TokenType.IMPORT,        # 36  TT_IMPORT
    TokenType.FROM,          # 37  TT_FROM
    TokenType.AS,            # 38  TT_AS
    TokenType.ATTEMPT,       # 39  TT_ATTEMPT
    TokenType.RESCUE,        # 40  TT_RESCUE
    TokenType.FINALLY,       # 41  TT_FINALLY
    TokenType.ALERT,         # 42  TT_ALERT
    TokenType.BREAK,         # 43  TT_BREAK
    TokenType.CONTINUE,      # 44  TT_CONTINUE
    TokenType.PASS,          # 45  TT_PASS
    TokenType.CLASS,         # 46  TT_CLASS
    TokenType.SELF,          # 47  TT_SELF
    TokenType.EXTENDS,       # 48  TT_EXTENDS
    TokenType.DOT,           # 49  TT_DOT
    TokenType.STRING,        # 50  TT_STRING
    TokenType.FSTRING,       # 51  TT_FSTRING
    TokenType.COMMA,         # 52  TT_COMMA
    TokenType.COLON,         # 53  TT_COLON
    TokenType.LBRACKET,      # 54  TT_LBRACKET
    TokenType.RBRACKET,      # 55  TT_RBRACKET
    TokenType.LBRACE,        # 56  TT_LBRACE
    TokenType.RBRACE,        # 57  TT_RBRACE
    TokenType.PLUS_ASSIGN,   # 58  TT_PLUS_ASSIGN
    TokenType.MINUS_ASSIGN,  # 59  TT_MINUS_ASSIGN
    TokenType.MUL_ASSIGN,    # 60  TT_MUL_ASSIGN
    TokenType.DIV_ASSIGN,    # 61  TT_DIV_ASSIGN
    TokenType.MOD_ASSIGN,    # 62  TT_MOD_ASSIGN
    TokenType.POW_ASSIGN,    # 63  TT_POW_ASSIGN
    TokenType.NULL_COALESCE, # 64  TT_NULL_COALESCE
    TokenType.NOT_IN,        # 65  TT_NOT_IN  (never emitted by the C lexer)
    TokenType.ELLIPSIS,      # 66  TT_ELLIPSIS
    TokenType.SWITCH,        # 67  TT_SWITCH
    TokenType.CASE,          # 68  TT_CASE
    TokenType.MATCH,         # 69  TT_MATCH
    TokenType.STEP,          # 70  TT_STEP
    TokenType.CONST,         # 71  TT_CONST
    TokenType.STRUCT,        # 72  TT_STRUCT
    TokenType.QUESTION,      # 73  TT_QUESTION
    TokenType.EOF,           # 74  TT_EOF
    # 75  TT_ERROR — no Python counterpart; raises InvalidTokenFault below
]

_TT_ERROR_IDX = len(_C_TO_PYTHON)   # == 75


# ── Public interface ──────────────────────────────────────────────────────────

def available() -> bool:
    """Return True if the C shared library loaded successfully."""
    return _lib is not None


def tokenize(source: str) -> list:
    """Lex *source* using the C library and return a list of Token objects.

    The returned list is identical in structure to what Lexer.get_tokens()
    produces — the rest of the pipeline (parser, interpreter) sees no
    difference between the two.

    Raises:
        InvalidTokenFault  — for illegal characters (TT_ERROR from C).
        RuntimeError       — if the library is not available.
    """
    if _lib is None:
        raise RuntimeError(
            f"C lexer library not found at '{_LIB_PATH}' — run 'make' in luz/c_lexer/"
        )

    # Encode the source to UTF-8 bytes.  The local variable keeps the bytes
    # object alive for the entire function so the C lexer's pointer stays valid.
    encoded = source.encode('utf-8')

    lex   = _CLexer()
    count = ctypes.c_int(0)

    _lib.lexer_init(ctypes.byref(lex), encoded)
    raw = _lib.lex_all(ctypes.byref(lex), ctypes.byref(count))

    if not raw:
        raise RuntimeError("lex_all() returned NULL — out of memory in C lexer")

    tokens = []
    n = count.value

    try:
        for i in range(n):
            ct     = raw[i]
            c_type = ct.type

            if c_type >= _TT_ERROR_IDX:
                # TT_ERROR — illegal character found in source
                char = ct.value.decode('utf-8') if ct.value else '?'
                e = InvalidTokenFault(f"Illegal character: '{char}'")
                e.line = ct.line
                e.col  = ct.col
                raise e

            py_type = _C_TO_PYTHON[c_type]

            # value is bytes when non-NULL; decode to str first.
            value = ct.value.decode('utf-8') if ct.value is not None else None

            # The parser expects INT values to be Python int objects and FLOAT
            # values to be Python float objects, matching the Python lexer's
            # make_number() behaviour.
            if py_type is TokenType.INT and value is not None:
                value = int(value)
            elif py_type is TokenType.FLOAT and value is not None:
                value = float(value)
            # The C lexer emits SELF without a value string; supply it so that
            # the rest of the pipeline (typechecker, error messages) can use
            # token.value == 'self' just like the Python lexer does.
            elif py_type is TokenType.SELF and value is None:
                value = 'self'

            tokens.append(Token(py_type, value, ct.line, ct.col))
    finally:
        # Always release C memory even if an exception was raised mid-loop
        _lib.free_tokens(raw, n)

    return tokens
