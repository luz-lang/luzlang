/* luz_lexer.c
 * 
 * Luz lexer implemented in C.
 * Compiled as a shared library (.dll / .so) and loaded by the python brigde
 * 
 * Stage 1 - Infrastructure only:
 *   lexer_init, advance, current_char, peek_char,
 *   skip_whitespace, skip_comment, lex_all (stub), free_tokens.
 * 
 * Later stages will fill lex_all() with actual token production.
 */

#include "luz_lexer.h"

#include <stdio.h>   /* printf - used only in the test main() */
#include <stdlib.h>  /* malloc, realloc, free */
#include <string.h>  /* strlen, strdup, strcmp */
#include <ctype.h>   /* isdigit, isalpha, isspace */

/* ── Internal helpers ────────────────────────────────────────────────────────
 * These four functions are the only war the rest of the lexer touches the
 * source string.  Keeping all bounds-checking here means every caller can
 * assume safety without repeating the same pos < lenght guard.
 */

/* current_char() returns the character at the current position, or '\0' when
 * the lexer has consumed every character.  '\0' is used as the EOF sentinel
 * because it cannot appear in valid Luz source (Luz strings use \0 escape
 * only inside string literals, which the lexe handles specially).
 */
static char current_char(const CLexer* lex) {
    if (lex->pos < lex->length)
        return lex->source[lex->pos];
    return '\0';
}

/* peek_char() looks one step ahead without consuming anything.
 * Used by operators that need lookahead: '=' could be ASSIGN or EE,
 * '*' could be MUL or POW, etc.
 * Returns '\0' if we are at the last character or past the end.
*/
static char peek_char(const CLexer* lex) {
    if (lex->pos + 1 < lex->length)
        return lex->source[lex->pos + 1];
    return '\0';
}

/* peek2_char() looks two steps ahead without consuming anything.
 * Needed for three-character tokens: '...' and '**='.
 * Returns '\0' if there are fewer than two characters remaining.
 */
static char peek2_char(const CLexer* lex) {
    if (lex->pos + 2 < lex->length)
        return lex->source[lex->pos + 2];
    return '\0';
}

/* advance() moves the position forward by one character and keeps line/col
 * in sync.  This is the single choke-point through which every consumed
 * character passes - the same design as the Python lexer.
 * 
 * When the current character is '\n':
 *   line is incremented and col is reset to 1 so that the NEXT character
 *   will be reported as column 1 of the new line.
 * For every other character:
 *   col is simply incremented.
 * 
 * Calling advance() when already at end-of-input is a no-op.
*/
static void advance(CLexer* lex) {
    if (lex->pos >= lex->length)
        return;
    if (lex->source[lex->pos] == '\n') {
        lex->line++;
        lex->col = 1;
    } else {
        lex->col++;
    }
    lex->pos++;
}

static void skip_whitespace(CLexer* lex) {
    while (current_char(lex) != '\0' && isspace((unsigned char)current_char(lex)))
        advance(lex);
}


static void skip_comment(CLexer* lex) {
    while (current_char(lex) != '\0' && current_char(lex) != '\n')
        advance(lex);
    advance(lex);   /* consume the '\n' */
}


static CToken make_token(TokenType type, int line, int col) {
    CToken t;
    t.type  = type;
    t.value = NULL;
    t.line  = line;
    t.col   = col;
    return t;
}


static CToken make_value_token(TokenType type, const char* value, int line, int col) {
    CToken t;
    t.type  = type;
    t.value = strdup(value);
    t.line  = line;
    t.col   = col;
    return t;
}



typedef struct {
    CToken* data;
    int     count;
    int     capacity;
} TokenArray;

static int tarray_init(TokenArray* arr) {
    arr->capacity = 64;
    arr->count    = 0;
    arr->data     = (CToken*)malloc(arr->capacity * sizeof(CToken));
    return arr->data != NULL;   /* 0 = allocation failed */
}


static int tarray_push(TokenArray* arr, CToken token) {
    if (arr->count == arr->capacity) {
        int new_cap   = arr->capacity * 2;
        CToken* grown = (CToken*)realloc(arr->data, new_cap * sizeof(CToken));
        if (grown == NULL) return 0; /* out of memory */
        arr->data     = grown;
        arr->capacity = new_cap;
    }
    arr->data[arr->count++] = token;
    return 1;
}


/* ── Stage 4: strings and format strings ────────────────────────────────────
 *
 * hex_val() converts a single hex character ('0'-'9', 'a'-'f', 'A'-'F') to
 * its integer value.  The caller must ensure the character is a valid hex
 * digit (isxdigit) before calling.
 */
static int hex_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return                            c - 'A' + 10;
}

/* utf8_encode() writes the UTF-8 byte sequence for a Unicode code point into
 * out[] and returns the number of bytes written (1-4).
 * Used by the \uXXXX escape sequence handler.
 */
static int utf8_encode(unsigned int cp, char* out) {
    if (cp < 0x80) {
        out[0] = (char)cp;
        return 1;
    }
    if (cp < 0x800) {
        out[0] = (char)(0xC0 | (cp >> 6));
        out[1] = (char)(0x80 | (cp & 0x3F));
        return 2;
    }
    if (cp < 0x10000) {
        out[0] = (char)(0xE0 | (cp >> 12));
        out[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
        out[2] = (char)(0x80 | (cp & 0x3F));
        return 3;
    }
    out[0] = (char)(0xF0 | (cp >> 18));
    out[1] = (char)(0x80 | ((cp >> 12) & 0x3F));
    out[2] = (char)(0x80 | ((cp >> 6)  & 0x3F));
    out[3] = (char)(0x80 | (cp & 0x3F));
    return 4;
}

/* lex_string() is called when current_char is '"'.
 * It allocates a buffer sized to the whole source (safe upper bound — no
 * string can be longer than the source itself), then fills it character by
 * character, resolving escape sequences along the way.
 *
 * Supported escapes:  \n  \t  \r  \\  \"  \xXX  \uXXXX
 *
 * On any error (unterminated, bad escape, bad hex digits) the buffer is
 * freed and a TT_ERROR token is returned so the Python side can report a
 * meaningful message.
 */
static CToken lex_string(CLexer* lex) {
    int   line = lex->line, col = lex->col;
    char* buf  = (char*)malloc(lex->length + 1);
    int   i    = 0;
    CToken t;

    if (buf == NULL)
        return make_value_token(TT_ERROR, "out of memory", line, col);

    advance(lex);   /* consume opening '"' */

    while (current_char(lex) != '\0' && current_char(lex) != '"') {
        if (current_char(lex) == '\\') {
            advance(lex);   /* consume '\' */
            char esc = current_char(lex);

            if (esc == '\0') {
                free(buf);
                return make_value_token(TT_ERROR, "unexpected end of string after '\\'", line, col);
            }

            if (esc == 'u') {
                /* \uXXXX — exactly 4 hex digits → UTF-8 bytes */
                unsigned int cp = 0;
                int j;
                advance(lex);   /* consume 'u' */
                for (j = 0; j < 4; j++) {
                    if (!isxdigit((unsigned char)current_char(lex))) {
                        free(buf);
                        return make_value_token(TT_ERROR, "\\u requires exactly 4 hex digits", line, col);
                    }
                    cp = cp * 16 + (unsigned int)hex_val(current_char(lex));
                    advance(lex);
                }
                i += utf8_encode(cp, buf + i);
                continue;
            }

            if (esc == 'x') {
                /* \xXX — exactly 2 hex digits → single byte */
                unsigned int cp = 0;
                int j;
                advance(lex);   /* consume 'x' */
                for (j = 0; j < 2; j++) {
                    if (!isxdigit((unsigned char)current_char(lex))) {
                        free(buf);
                        return make_value_token(TT_ERROR, "\\x requires exactly 2 hex digits", line, col);
                    }
                    cp = cp * 16 + (unsigned int)hex_val(current_char(lex));
                    advance(lex);
                }
                buf[i++] = (char)cp;
                continue;
            }

            /* Simple single-character escapes */
            switch (esc) {
                case 'n':  buf[i++] = '\n'; break;
                case 't':  buf[i++] = '\t'; break;
                case 'r':  buf[i++] = '\r'; break;
                case '\\': buf[i++] = '\\'; break;
                case '"':  buf[i++] = '"';  break;
                default:
                    free(buf);
                    return make_value_token(TT_ERROR, "unknown escape sequence", line, col);
            }
            advance(lex);   /* consume the escape letter */
            continue;
        }

        buf[i++] = current_char(lex);
        advance(lex);
    }

    if (current_char(lex) != '"') {
        free(buf);
        return make_value_token(TT_ERROR, "unterminated string literal", line, col);
    }
    advance(lex);   /* consume closing '"' */

    buf[i] = '\0';
    t = make_value_token(TT_STRING, buf, line, col);
    free(buf);
    return t;
}


/* lex_fstring() is called after the '$' has already been consumed and
 * current_char is confirmed to be '"'.
 * It works like lex_string() with two differences:
 *   1. Content inside { } is copied verbatim (no escape processing) so the
 *      parser receives the raw embedded expression text.
 *   2. The closing '"' is only recognised when brace_depth is zero.
 * Only the basic five escapes are supported outside braces (\n \t \r \\ \").
 * \uXXXX and \xXX are not supported in format strings (matches Python lexer).
 */
static CToken lex_fstring(CLexer* lex, int line, int col) {
    char* buf        = (char*)malloc(lex->length + 1);
    int   i          = 0;
    int   brace_depth = 0;
    CToken t;

    if (buf == NULL)
        return make_value_token(TT_ERROR, "out of memory", line, col);

    advance(lex);   /* consume opening '"' */

    while (current_char(lex) != '\0') {
        char c = current_char(lex);

        /* Closing quote only ends the string when we are outside all braces */
        if (brace_depth == 0 && c == '"')
            break;

        if (c == '{') { brace_depth++; buf[i++] = c; advance(lex); continue; }
        if (c == '}') { brace_depth--; buf[i++] = c; advance(lex); continue; }

        /* Escape sequences only apply outside braces */
        if (c == '\\' && brace_depth == 0) {
            advance(lex);   /* consume '\' */
            char esc = current_char(lex);
            if (esc == '\0') {
                free(buf);
                return make_value_token(TT_ERROR, "unterminated format string after '\\'", line, col);
            }
            switch (esc) {
                case 'n':  buf[i++] = '\n'; break;
                case 't':  buf[i++] = '\t'; break;
                case 'r':  buf[i++] = '\r'; break;
                case '\\': buf[i++] = '\\'; break;
                case '"':  buf[i++] = '"';  break;
                default:
                    free(buf);
                    return make_value_token(TT_ERROR, "unknown escape sequence in format string", line, col);
            }
            advance(lex);   /* consume the escape letter */
            continue;
        }

        buf[i++] = c;
        advance(lex);
    }

    if (current_char(lex) != '"') {
        free(buf);
        return make_value_token(TT_ERROR, "unterminated format string", line, col);
    }
    advance(lex);   /* consume closing '"' */

    buf[i] = '\0';
    t = make_value_token(TT_FSTRING, buf, line, col);
    free(buf);
    return t;
}


/* ── Stage 3: identifiers and keywords ──────────────────────────────────────
 *
 * Keyword table: a flat array of (string, TokenType) pairs.
 * Linear search is fine — there are ~30 keywords and this runs once per
 * identifier token.  The last entry uses NULL as a sentinel to mark the end.
 */
typedef struct { const char* word; TokenType type; } Keyword;

static const Keyword KEYWORDS[] = {
    { "if",       TT_IF       },
    { "elif",     TT_ELIF     },
    { "else",     TT_ELSE     },
    { "while",    TT_WHILE    },
    { "for",      TT_FOR      },
    { "to",       TT_TO       },
    { "in",       TT_IN       },
    { "step",     TT_STEP     },
    { "true",     TT_TRUE     },
    { "false",    TT_FALSE    },
    { "null",     TT_NULL     },
    { "and",      TT_AND      },
    { "or",       TT_OR       },
    { "not",      TT_NOT      },
    { "function", TT_FUNCTION },
    { "return",   TT_RETURN   },
    { "fn",       TT_FN       },
    { "import",   TT_IMPORT   },
    { "from",     TT_FROM     },
    { "as",       TT_AS       },
    { "attempt",  TT_ATTEMPT  },
    { "rescue",   TT_RESCUE   },
    { "finally",  TT_FINALLY  },
    { "alert",    TT_ALERT    },
    { "break",    TT_BREAK    },
    { "continue", TT_CONTINUE },
    { "pass",     TT_PASS     },
    { "class",    TT_CLASS    },
    { "self",     TT_SELF     },
    { "extends",  TT_EXTENDS  },
    { "switch",   TT_SWITCH   },
    { "case",     TT_CASE     },
    { "match",    TT_MATCH    },
    { "const",    TT_CONST    },
    { NULL,       TT_EOF      }   /* sentinel */
};


/* lex_identifier() is called when current_char is a letter or '_'.
 * It reads the full word (letters, digits, underscores), then walks the
 * keyword table.  If there is a match it returns a valueless keyword token;
 * otherwise it returns TT_IDENTIFIER with the word as its value string so
 * the parser can recover the variable or function name.
 */
static CToken lex_identifier(CLexer* lex) {
    int  line = lex->line, col = lex->col;
    char buf[256];
    int  i = 0;
    const Keyword* kw;

    while (current_char(lex) != '\0' &&
           (isalnum((unsigned char)current_char(lex)) || current_char(lex) == '_')) {
        buf[i++] = current_char(lex);
        advance(lex);
    }
    buf[i] = '\0';

    /* Linear keyword search */
    for (kw = KEYWORDS; kw->word != NULL; kw++) {
        if (strcmp(buf, kw->word) == 0)
            return make_token(kw->type, line, col);
    }

    return make_value_token(TT_IDENTIFIER, buf, line, col);
}


/* ── Stage 2: numbers and operators ─────────────────────────────────────────*/

/* lex_number() is called when current_char is a digit.
 * It consumes all consecutive digits, then checks for a decimal point
 * followed by at least one more digit (a bare trailing dot, e.g. "1.",
 * is NOT a float — it would be an integer followed by a DOT token).
 * The collected characters are stored in a fixed-size local buffer;
 * 63 digits is far more than any realistic numeric literal needs.
 */
static CToken lex_number(CLexer* lex) {
    int line = lex->line, col = lex->col;
    char buf[64];
    int  i = 0;
    int  is_float = 0;

    /* Consume the integer part */
    while (current_char(lex) != '\0' && isdigit((unsigned char)current_char(lex))) {
        buf[i++] = current_char(lex);
        advance(lex);
    }

    /* Optional fractional part: dot followed by at least one digit */
    if (current_char(lex) == '.' && isdigit((unsigned char)peek_char(lex))) {
        is_float    = 1;
        buf[i++]    = '.';
        advance(lex);   /* consume the '.' */
        while (current_char(lex) != '\0' && isdigit((unsigned char)current_char(lex))) {
            buf[i++] = current_char(lex);
            advance(lex);
        }
    }

    buf[i] = '\0';
    return make_value_token(is_float ? TT_FLOAT : TT_INT, buf, line, col);
}


/* lex_operator() is called for any character that is not whitespace, a
 * comment, a digit, a letter or a quote.  It reads current_char (and up
 * to two chars ahead) to decide which token to emit, then advances past
 * every character it consumed.
 *
 * Single-char tokens (LPAREN, COMMA, …) advance once.
 * Two-char tokens (EE, POW, ARROW, …) advance twice.
 * Three-char tokens (ELLIPSIS, POW_ASSIGN) advance three times.
 *
 * '!' alone and '?' alone are illegal in Luz; they produce TT_ERROR so
 * the Python side can report a meaningful message.
 */
static CToken lex_operator(CLexer* lex) {
    int  line = lex->line, col = lex->col;
    char c    = current_char(lex);
    char p    = peek_char(lex);
    char p2   = peek2_char(lex);
    char buf[2];

    switch (c) {
        case '+':
            advance(lex);
            if (p == '=') { advance(lex); return make_token(TT_PLUS_ASSIGN,  line, col); }
            return make_token(TT_PLUS, line, col);

        case '-':
            advance(lex);
            if (p == '=') { advance(lex); return make_token(TT_MINUS_ASSIGN, line, col); }
            if (p == '>') { advance(lex); return make_token(TT_ARROW,        line, col); }
            return make_token(TT_MINUS, line, col);

        case '*':
            advance(lex);
            if (p == '*') {
                advance(lex);
                if (p2 == '=') { advance(lex); return make_token(TT_POW_ASSIGN, line, col); }
                return make_token(TT_POW, line, col);
            }
            if (p == '=') { advance(lex); return make_token(TT_MUL_ASSIGN, line, col); }
            return make_token(TT_MUL, line, col);

        case '/':
            advance(lex);
            if (p == '/') { advance(lex); return make_token(TT_IDIV,       line, col); }
            if (p == '=') { advance(lex); return make_token(TT_DIV_ASSIGN, line, col); }
            return make_token(TT_DIV, line, col);

        case '%':
            advance(lex);
            if (p == '=') { advance(lex); return make_token(TT_MOD_ASSIGN, line, col); }
            return make_token(TT_MOD, line, col);

        case '=':
            advance(lex);
            if (p == '=') { advance(lex); return make_token(TT_EE,    line, col); }
            if (p == '>') { advance(lex); return make_token(TT_ARROW,  line, col); }
            return make_token(TT_ASSIGN, line, col);

        case '!':
            advance(lex);
            if (p == '=') { advance(lex); return make_token(TT_NE, line, col); }
            buf[0] = c; buf[1] = '\0';
            return make_value_token(TT_ERROR, buf, line, col);

        case '<':
            advance(lex);
            if (p == '=') { advance(lex); return make_token(TT_LTE, line, col); }
            return make_token(TT_LT, line, col);

        case '>':
            advance(lex);
            if (p == '=') { advance(lex); return make_token(TT_GTE, line, col); }
            return make_token(TT_GT, line, col);

        case '?':
            advance(lex);
            if (p == '?') { advance(lex); return make_token(TT_NULL_COALESCE, line, col); }
            buf[0] = c; buf[1] = '\0';
            return make_value_token(TT_ERROR, buf, line, col);

        case '.':
            advance(lex);
            if (p == '.' && p2 == '.') {
                advance(lex); advance(lex);
                return make_token(TT_ELLIPSIS, line, col);
            }
            return make_token(TT_DOT, line, col);

        case '(': advance(lex); return make_token(TT_LPAREN,   line, col);
        case ')': advance(lex); return make_token(TT_RPAREN,   line, col);
        case '[': advance(lex); return make_token(TT_LBRACKET, line, col);
        case ']': advance(lex); return make_token(TT_RBRACKET, line, col);
        case '{': advance(lex); return make_token(TT_LBRACE,   line, col);
        case '}': advance(lex); return make_token(TT_RBRACE,   line, col);
        case ',': advance(lex); return make_token(TT_COMMA,    line, col);
        case ':': advance(lex); return make_token(TT_COLON,    line, col);

        default:
            buf[0] = c; buf[1] = '\0';
            advance(lex);
            return make_value_token(TT_ERROR, buf, line, col);
    }
}


/*── Public API ──────────────────────────────────────────────────────────────*/

void lexer_init(CLexer* lex, const char* source) {
    lex->source = source;
    lex->pos    = 0;
    lex->line   = 1;
    lex->col    = 1;
    lex->length = (int)strlen(source);
}


void free_tokens(CToken* tokens, int count) {
    int i;
    for (i = 0; i < count; i++) {
        if (tokens[i].value != NULL)
            free(tokens[i].value);
    }
    free(tokens);
}

CToken* lex_all(CLexer* lex, int* out_count) {
    TokenArray arr;
    if (!tarray_init(&arr)) {
        *out_count = 0;
        return NULL;
    }

    while (current_char(lex) != '\0') {
        /* Skip whitespace - produces no tokens */
        if (isspace((unsigned char)current_char(lex))) {
            skip_whitespace(lex);
            continue;
        }

        /* Skip line comments */
        if (current_char(lex) == '#') {
            skip_comment(lex);
            continue;
        }

        /* Regular strings */
        if (current_char(lex) == '"') {
            tarray_push(&arr, lex_string(lex));
            continue;
        }

        /* Format strings: '$"..."' — consume '$', then delegate */
        if (current_char(lex) == '$') {
            int fline = lex->line, fcol = lex->col;
            advance(lex);   /* consume '$' */
            if (current_char(lex) != '"') {
                tarray_push(&arr, make_value_token(TT_ERROR, "$", fline, fcol));
                continue;
            }
            tarray_push(&arr, lex_fstring(lex, fline, fcol));
            continue;
        }

        /* Identifiers and keywords */
        if (isalpha((unsigned char)current_char(lex)) || current_char(lex) == '_') {
            tarray_push(&arr, lex_identifier(lex));
            continue;
        }

        /* Numeric literals */
        if (isdigit((unsigned char)current_char(lex))) {
            tarray_push(&arr, lex_number(lex));
            continue;
        }

        /* Operators and punctuation */
        tarray_push(&arr, lex_operator(lex));
    }

    tarray_push(&arr, make_token(TT_EOF, lex->line, lex->col));

    *out_count = arr.count;
    return arr.data;
}



/* ── Test main ───────────────────────────────────────────────────────────────
*/
#ifdef LUZ_TEST

static const char* token_type_name(TokenType t) {
    switch (t) {
        case TT_INT:          return "INT";
        case TT_FLOAT:        return "FLOAT";
        case TT_PLUS:         return "PLUS";
        case TT_MINUS:        return "MINUS";
        case TT_MUL:          return "MUL";
        case TT_DIV:          return "DIV";
        case TT_MOD:          return "MOD";
        case TT_POW:          return "POW";
        case TT_IDIV:         return "IDIV";
        case TT_ASSIGN:       return "ASSIGN";
        case TT_EE:           return "EE";
        case TT_NE:           return "NE";
        case TT_LT:           return "LT";
        case TT_GT:           return "GT";
        case TT_LTE:          return "LTE";
        case TT_GTE:          return "GTE";
        case TT_PLUS_ASSIGN:  return "PLUS_ASSIGN";
        case TT_MINUS_ASSIGN: return "MINUS_ASSIGN";
        case TT_MUL_ASSIGN:   return "MUL_ASSIGN";
        case TT_DIV_ASSIGN:   return "DIV_ASSIGN";
        case TT_MOD_ASSIGN:   return "MOD_ASSIGN";
        case TT_POW_ASSIGN:   return "POW_ASSIGN";
        case TT_ARROW:        return "ARROW";
        case TT_NULL_COALESCE:return "NULL_COALESCE";
        case TT_DOT:          return "DOT";
        case TT_ELLIPSIS:     return "ELLIPSIS";
        case TT_LPAREN:       return "LPAREN";
        case TT_RPAREN:       return "RPAREN";
        case TT_LBRACKET:     return "LBRACKET";
        case TT_RBRACKET:     return "RBRACKET";
        case TT_LBRACE:       return "LBRACE";
        case TT_RBRACE:       return "RBRACE";
        case TT_COMMA:        return "COMMA";
        case TT_COLON:        return "COLON";
        case TT_STRING:       return "STRING";
        case TT_FSTRING:      return "FSTRING";
        case TT_IDENTIFIER:   return "IDENTIFIER";
        case TT_IF:           return "IF";
        case TT_ELIF:         return "ELIF";
        case TT_ELSE:         return "ELSE";
        case TT_WHILE:        return "WHILE";
        case TT_FOR:          return "FOR";
        case TT_TO:           return "TO";
        case TT_IN:           return "IN";
        case TT_STEP:         return "STEP";
        case TT_TRUE:         return "TRUE";
        case TT_FALSE:        return "FALSE";
        case TT_NULL:         return "NULL";
        case TT_AND:          return "AND";
        case TT_OR:           return "OR";
        case TT_NOT:          return "NOT";
        case TT_FUNCTION:     return "FUNCTION";
        case TT_RETURN:       return "RETURN";
        case TT_FN:           return "FN";
        case TT_IMPORT:       return "IMPORT";
        case TT_FROM:         return "FROM";
        case TT_AS:           return "AS";
        case TT_ATTEMPT:      return "ATTEMPT";
        case TT_RESCUE:       return "RESCUE";
        case TT_FINALLY:      return "FINALLY";
        case TT_ALERT:        return "ALERT";
        case TT_BREAK:        return "BREAK";
        case TT_CONTINUE:     return "CONTINUE";
        case TT_PASS:         return "PASS";
        case TT_CLASS:        return "CLASS";
        case TT_SELF:         return "SELF";
        case TT_EXTENDS:      return "EXTENDS";
        case TT_SWITCH:       return "SWITCH";
        case TT_CASE:         return "CASE";
        case TT_MATCH:        return "MATCH";
        case TT_CONST:        return "CONST";
        case TT_EOF:          return "EOF";
        case TT_ERROR:        return "ERROR";
        default:              return "UNKNOWN";
    }
}

/* Helper: print every token in an array and free it */
static void print_and_free(CToken* tokens, int count) {
    int i;
    for (i = 0; i < count; i++) {
        if (tokens[i].value)
            printf("  [%d] %-14s value=%-10s line=%d col=%d\n",
                   i, token_type_name(tokens[i].type),
                   tokens[i].value, tokens[i].line, tokens[i].col);
        else
            printf("  [%d] %-14s line=%d col=%d\n",
                   i, token_type_name(tokens[i].type),
                   tokens[i].line, tokens[i].col);
    }
    free_tokens(tokens, count);
}

int main(void) {
    CLexer  lex;
    CToken* tokens;
    int     count;

    /* ── Test 1: integer literal ─────────────────────────────────────── */
    printf("Test 1: integer\n");
    lexer_init(&lex, "42");
    tokens = lex_all(&lex, &count);
    printf("  expect: INT(42)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 2: float literal ───────────────────────────────────────── */
    printf("\nTest 2: float\n");
    lexer_init(&lex, "3.14");
    tokens = lex_all(&lex, &count);
    printf("  expect: FLOAT(3.14)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 3: bare dot is NOT a float ─────────────────────────────── */
    printf("\nTest 3: trailing dot stays INT + DOT\n");
    lexer_init(&lex, "1.");
    tokens = lex_all(&lex, &count);
    printf("  expect: INT(1)  DOT  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 4: simple expression ───────────────────────────────────── */
    printf("\nTest 4: simple expression\n");
    lexer_init(&lex, "1 + 2 * 3");
    tokens = lex_all(&lex, &count);
    printf("  expect: INT(1) PLUS INT(2) MUL INT(3) EOF\n");
    print_and_free(tokens, count);

    /* ── Test 5: two-char operators ──────────────────────────────────── */
    printf("\nTest 5: two-char operators\n");
    lexer_init(&lex, "== != <= >= ** // -> ??");
    tokens = lex_all(&lex, &count);
    printf("  expect: EE NE LTE GTE POW IDIV ARROW NULL_COALESCE EOF\n");
    print_and_free(tokens, count);

    /* ── Test 6: compound assignment ─────────────────────────────────── */
    printf("\nTest 6: compound assignment\n");
    lexer_init(&lex, "+= -= *= /= %= **=");
    tokens = lex_all(&lex, &count);
    printf("  expect: PLUS_ASSIGN MINUS_ASSIGN MUL_ASSIGN DIV_ASSIGN MOD_ASSIGN POW_ASSIGN EOF\n");
    print_and_free(tokens, count);

    /* ── Test 7: ellipsis vs dot ─────────────────────────────────────── */
    printf("\nTest 7: ellipsis vs dot\n");
    lexer_init(&lex, "... .");
    tokens = lex_all(&lex, &count);
    printf("  expect: ELLIPSIS DOT EOF\n");
    print_and_free(tokens, count);

    /* ── Test 8: column tracking across operators ─────────────────────── */
    printf("\nTest 8: column tracking\n");
    lexer_init(&lex, "1 + 20");
    tokens = lex_all(&lex, &count);
    printf("  expect: INT col=1, PLUS col=3, INT col=5, EOF\n");
    print_and_free(tokens, count);

    /* ── Test 9: plain identifier ────────────────────────────────────────── */
    printf("\nTest 9: identifier\n");
    lexer_init(&lex, "myVar");
    tokens = lex_all(&lex, &count);
    printf("  expect: IDENTIFIER(myVar)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 10: keywords are not identifiers ───────────────────────────── */
    printf("\nTest 10: keywords\n");
    lexer_init(&lex, "if while function return true false null");
    tokens = lex_all(&lex, &count);
    printf("  expect: IF WHILE FUNCTION RETURN TRUE FALSE NULL EOF\n");
    print_and_free(tokens, count);

    /* ── Test 11: keyword prefix is still an identifier ──────────────────── */
    printf("\nTest 11: keyword-prefix identifier\n");
    lexer_init(&lex, "iffy forLoop");
    tokens = lex_all(&lex, &count);
    printf("  expect: IDENTIFIER(iffy)  IDENTIFIER(forLoop)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 12: real Luz statement ─────────────────────────────────────── */
    printf("\nTest 12: assignment statement\n");
    lexer_init(&lex, "x = 1 + y");
    tokens = lex_all(&lex, &count);
    printf("  expect: IDENTIFIER(x) ASSIGN INT(1) PLUS IDENTIFIER(y) EOF\n");
    print_and_free(tokens, count);

    /* ── Test 13: underscore identifier ─────────────────────────────────── */
    printf("\nTest 13: underscore identifier\n");
    lexer_init(&lex, "_private _x2");
    tokens = lex_all(&lex, &count);
    printf("  expect: IDENTIFIER(_private)  IDENTIFIER(_x2)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 14: simple string ──────────────────────────────────────────── */
    printf("\nTest 14: simple string\n");
    lexer_init(&lex, "\"hello\"");
    tokens = lex_all(&lex, &count);
    printf("  expect: STRING(hello)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 15: escape sequences ───────────────────────────────────────── */
    printf("\nTest 15: escape sequences\n");
    lexer_init(&lex, "\"a\\nb\\tc\"");
    tokens = lex_all(&lex, &count);
    printf("  expect: STRING with newline and tab embedded\n");
    if (count >= 1 && tokens[0].value) {
        printf("  value bytes: ");
        int j;
        for (j = 0; tokens[0].value[j] != '\0'; j++)
            printf("%d ", (unsigned char)tokens[0].value[j]);
        printf("  (expect: 97 10 98 9 99)\n");
    }
    print_and_free(tokens, count);

    /* ── Test 16: hex escape ─────────────────────────────────────────────── */
    printf("\nTest 16: \\x41 = 'A'\n");
    lexer_init(&lex, "\"\\x41\"");
    tokens = lex_all(&lex, &count);
    printf("  expect: STRING(A)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 17: unicode escape ─────────────────────────────────────────── */
    printf("\nTest 17: \\u0041 = 'A'\n");
    lexer_init(&lex, "\"\\u0041\"");
    tokens = lex_all(&lex, &count);
    printf("  expect: STRING(A)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 18: format string ──────────────────────────────────────────── */
    printf("\nTest 18: format string\n");
    lexer_init(&lex, "$\"hello {name}!\"");
    tokens = lex_all(&lex, &count);
    printf("  expect: FSTRING(hello {name}!)  EOF\n");
    print_and_free(tokens, count);

    /* ── Test 19: real Luz snippet with strings ───────────────────────────── */
    printf("\nTest 19: Luz snippet\n");
    lexer_init(&lex, "x = \"world\"");
    tokens = lex_all(&lex, &count);
    printf("  expect: IDENTIFIER(x) ASSIGN STRING(world) EOF\n");
    print_and_free(tokens, count);

    printf("\nStage 2 OK\n");
    return 0;
}

#endif /* LUZ_TEST */