/* luz_lexer.h
*
   * Public interface for the Luz lexer written in C.
   *
   * Role in the pipeline:
   *   Source text (char*) -> [lex_all()] -> CToken[] -> Python bridge -> Token[]
   *
   * This header defines three things:
   *   1. TokenType  — an enum with one member per distinct token kind.
   *                   The names mirror Python's TokenType exactly so the bridge
   *                   can map between them without a lookup table.
   *   2. CToken     — the value object the lexer produces: type + value string
   *                   + source position.
   *   3. CLexer     — the mutable state the lexer carries while scanning:
   *                   a pointer into the source, current position, line, col.
   *
   * Memory model:
   *   lex_all() returns a heap-allocated array of CToken.
   *   Each CToken whose value field is non-NULL owns that string (also heap).
   *   Call free_tokens() when done — it frees every value string and then the
   *   array itself.
   *   The source string passed to lexer_init() is NOT owned by the lexer;
   *   the caller is responsible for keeping it alive while the lexer runs.
   */

#ifndef LUZ_LEXER_H
#define LUZ_LEXER_H

/* ── Token types ─────────────────────────────────────────────────────────────
 * One entry per distinct token kind, in the same order as Python's TokenType.
 * We do NOT rely on the numeric values matching Python's auto() integers —
 * the bridge translates by name.  TT_ERROR is a C-only sentinel returned
 * when an illegal character is found; it has no Python counterpart and is
 * never passed to the parser.
 */
typedef enum {
    /* Numeric literals */
    TT_INT = 0,
    TT_FLOAT,

    /* Arithmetic operators */
    TT_PLUS,
    TT_MINUS,
    TT_MUL,
    TT_DIV,
    TT_MOD,
    TT_POW,
    TT_IDIV,

    /* Grouping */
    TT_LPAREN,
    TT_RPAREN,

    /* Identifiers and assignment */
    TT_IDENTIFIER,
    TT_ASSIGN,

    /* Comparison operators */
    TT_EE,
    TT_NE,
    TT_LT,
    TT_GT,
    TT_LTE,
    TT_GTE,

    /* Control-flow keywords */
    TT_IF,
    TT_ELIF,
    TT_ELSE,
    TT_WHILE,
    TT_FOR,
    TT_TO,
    TT_IN,

    /* Boolean and null literals */
    TT_TRUE,
    TT_FALSE,
    TT_NULL,

    /* Logical operators */
    TT_AND,
    TT_OR,
    TT_NOT,

    /* Functions */
    TT_FUNCTION,
    TT_RETURN,
    TT_FN,
    TT_ARROW,

    /* Module system */
    TT_IMPORT,
    TT_FROM,
    TT_AS,

    /* Error handling */
    TT_ATTEMPT,
    TT_RESCUE,
    TT_FINALLY,
    TT_ALERT,

    /* Loop control */
    TT_BREAK,
    TT_CONTINUE,
    TT_PASS,

    /* Object-oriented */
    TT_CLASS,
    TT_SELF,
    TT_EXTENDS,
    TT_DOT,

    /* String literals */
    TT_STRING,
    TT_FSTRING,

    /* Punctuation */
    TT_COMMA,
    TT_COLON,
    TT_LBRACKET,
    TT_RBRACKET,
    TT_LBRACE,
    TT_RBRACE,

    /* Compound assignment */
    TT_PLUS_ASSIGN,
    TT_MINUS_ASSIGN,
    TT_MUL_ASSIGN,
    TT_DIV_ASSIGN,
    TT_MOD_ASSIGN,
    TT_POW_ASSIGN,

    /* Special operators */
    TT_NULL_COALESCE,
    TT_NOT_IN,
    TT_ELLIPSIS,

    /* Switch / Match */
    TT_SWITCH,
    TT_CASE,
    TT_MATCH,

    /* For step */
    TT_STEP,

    /* Constants */
    TT_CONST,

    /* Structs */
    TT_STRUCT,

    /* Sentinels */
    TT_EOF,
    TT_ERROR   /* illegal character - never reaches Python*/
} TokenType;


/* ── CToken ──────────────────────────────────────────────────────────────────
 * The value object produced by the lexer.  Mirrors Python's Token class.
 *
 * value:
 *   Heap-allocated null-terminated string.  Non-NULL only for tokens that
 *   carry a payload: TT_INT, TT_FLOAT, TT_IDENTIFIER, TT_SELF, TT_STRING,
 *   TT_FSTRING, and TT_ERROR (carries the offending character).
 *   All other tokens set value = NULL because the type alone is enough.
 *
 * line / col:
 *   1-based source position of the first character of the token.
 */

typedef struct {
    TokenType type;
    char*     value;
    int       line;
    int       col;
} CToken;


/* ── CLexer ──────────────────────────────────────────────────────────────────
 * Mutable scanner state.  Callers allocate this on the stack and pass a
 * pointer to lexer_init(), which fills every field.
 *
 * source:
 *   Pointer to the source text.  The lexer does NOT own this memory.
 * pos:
 *   Index of the current character (0-based).  When pos == length the lexer
 *   has reached end-of-input; current_char() returns '\0'.
 * line / col:
 *   Current source position, updated by advance().  These are copied into
 *   each CToken at the moment the token starts.
 * length:
 *   Cached strlen(source) so the hot loop never recomputes it.
 */


typedef struct {
    const char* source;
    int         pos;
    int         line;
    int         col;
    int         length;
} CLexer;


/* ── Public API ──────────────────────────────────────────────────────────────
 *
 * lexer_init  — fill a CLexer from a source string.  Must be called before
 *               any other function.
 *
 * lex_all     — run the full scan and return a heap-allocated array of
 *               CToken.  The array always ends with a TT_EOF token.
 *               *out_count receives the number of tokens INCLUDING the EOF.
 *               Returns NULL on allocation failure (out of memory).
 *
 * free_tokens — release every value string inside the array and then the
 *               array itself.  Always call this after lex_all().
 */
void    lexer_init  (CLexer* lex, const char* source);
CToken* lex_all     (CLexer* lex, int* out_count);
void    free_tokens (CToken* tokens, int count);

#endif /* LUZ_LEXER_H */