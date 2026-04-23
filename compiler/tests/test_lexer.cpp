#include "test_runner.hpp"

#include "luz/lexer.hpp"
#include "luz/token.hpp"

extern "C" {
#include "luz_lexer.h"
}

using namespace luz;

// ── helpers ──────────────────────────────────────────────────────────────────

static std::vector<Token> lex_skip_eof(const std::string& src) {
    auto tokens = luz::lex(src);
    if (!tokens.empty() && tokens.back().is(TT_EOF))
        tokens.pop_back();
    return tokens;
}

static Token single(const std::string& src) {
    auto toks = lex_skip_eof(src);
    REQUIRE(toks.size() == 1);
    return toks[0];
}

// ── numeric literals ─────────────────────────────────────────────────────────

TEST_CASE("Lexer: integer literal") {
    auto t = single("42");
    CHECK(t.type  == TT_INT);
    CHECK(t.value == "42");
}

TEST_CASE("Lexer: float literal") {
    auto t = single("3.14");
    CHECK(t.type  == TT_FLOAT);
    CHECK(t.value == "3.14");
}

TEST_CASE("Lexer: negative integer is minus then int") {
    auto toks = lex_skip_eof("-7");
    REQUIRE(toks.size() == 2);
    CHECK(toks[0].type  == TT_MINUS);
    CHECK(toks[1].type  == TT_INT);
    CHECK(toks[1].value == "7");
}

// ── string literals ───────────────────────────────────────────────────────────

TEST_CASE("Lexer: string literal") {
    auto t = single("\"hello world\"");
    CHECK(t.type  == TT_STRING);
    CHECK(t.value == "hello world");
}

TEST_CASE("Lexer: empty string") {
    auto t = single("\"\"");
    CHECK(t.type  == TT_STRING);
    CHECK(t.value == "");
}

TEST_CASE("Lexer: f-string literal") {
    auto t = single("$\"hello {name}\"");
    CHECK(t.type == TT_FSTRING);
}

// ── boolean / null ────────────────────────────────────────────────────────────

TEST_CASE("Lexer: true literal")  { CHECK(single("true").type  == TT_TRUE);  }
TEST_CASE("Lexer: false literal") { CHECK(single("false").type == TT_FALSE); }
TEST_CASE("Lexer: null literal")  { CHECK(single("null").type  == TT_NULL);  }

// ── arithmetic operators ──────────────────────────────────────────────────────

TEST_CASE("Lexer: arithmetic operators") {
    struct Case { const char* src; TokenType tt; };
    Case cases[] = {
        {"+",  TT_PLUS},
        {"-",  TT_MINUS},
        {"*",  TT_MUL},
        {"/",  TT_DIV},
        {"%",  TT_MOD},
        {"**", TT_POW},
        {"//", TT_IDIV},
    };
    for (auto& c : cases)
        CHECK(single(c.src).type == c.tt);
}

// ── comparison operators ──────────────────────────────────────────────────────

TEST_CASE("Lexer: comparison operators") {
    struct Case { const char* src; TokenType tt; };
    Case cases[] = {
        {"==", TT_EE},
        {"!=", TT_NE},
        {"<",  TT_LT},
        {">",  TT_GT},
        {"<=", TT_LTE},
        {">=", TT_GTE},
    };
    for (auto& c : cases)
        CHECK(single(c.src).type == c.tt);
}

// ── compound assignment ───────────────────────────────────────────────────────

TEST_CASE("Lexer: compound assignment operators") {
    struct Case { const char* src; TokenType tt; };
    Case cases[] = {
        {"+=",  TT_PLUS_ASSIGN},
        {"-=",  TT_MINUS_ASSIGN},
        {"*=",  TT_MUL_ASSIGN},
        {"/=",  TT_DIV_ASSIGN},
        {"%=",  TT_MOD_ASSIGN},
        {"**=", TT_POW_ASSIGN},
    };
    for (auto& c : cases)
        CHECK(single(c.src).type == c.tt);
}

// ── keywords ──────────────────────────────────────────────────────────────────

TEST_CASE("Lexer: keywords") {
    struct Case { const char* src; TokenType tt; };
    Case cases[] = {
        {"if",       TT_IF},
        {"elif",     TT_ELIF},
        {"else",     TT_ELSE},
        {"while",    TT_WHILE},
        {"for",      TT_FOR},
        {"to",       TT_TO},
        {"in",       TT_IN},
        {"return",   TT_RETURN},
        {"function", TT_FUNCTION},
        {"fn",       TT_FN},
        {"break",    TT_BREAK},
        {"continue", TT_CONTINUE},
        {"pass",     TT_PASS},
        {"class",    TT_CLASS},
        {"extends",  TT_EXTENDS},
        {"import",   TT_IMPORT},
        {"from",     TT_FROM},
        {"as",       TT_AS},
        {"attempt",  TT_ATTEMPT},
        {"rescue",   TT_RESCUE},
        {"finally",  TT_FINALLY},
        {"alert",    TT_ALERT},
        {"switch",   TT_SWITCH},
        {"case",     TT_CASE},
        {"match",    TT_MATCH},
        {"step",     TT_STEP},
        {"const",    TT_CONST},
        {"struct",   TT_STRUCT},
        {"and",      TT_AND},
        {"or",       TT_OR},
        {"not",      TT_NOT},
    };
    for (auto& c : cases)
        CHECK(single(c.src).type == c.tt);
}

// ── identifiers ───────────────────────────────────────────────────────────────

TEST_CASE("Lexer: identifier") {
    auto t = single("myVar");
    CHECK(t.type  == TT_IDENTIFIER);
    CHECK(t.value == "myVar");
}

TEST_CASE("Lexer: underscore identifier") {
    auto t = single("_private");
    CHECK(t.type  == TT_IDENTIFIER);
    CHECK(t.value == "_private");
}

// ── punctuation ───────────────────────────────────────────────────────────────

TEST_CASE("Lexer: punctuation") {
    struct Case { const char* src; TokenType tt; };
    Case cases[] = {
        {"(", TT_LPAREN},
        {")", TT_RPAREN},
        {"[", TT_LBRACKET},
        {"]", TT_RBRACKET},
        {"{", TT_LBRACE},
        {"}", TT_RBRACE},
        {",", TT_COMMA},
        {":", TT_COLON},
        {".", TT_DOT},
        {"?", TT_QUESTION},
    };
    for (auto& c : cases)
        CHECK(single(c.src).type == c.tt);
}

// ── source position ───────────────────────────────────────────────────────────

TEST_CASE("Lexer: first token at line 1 col 1") {
    auto toks = luz::lex("42");
    REQUIRE_FALSE(toks.empty());
    CHECK(toks[0].line == 1);
    CHECK(toks[0].col  == 1);
}

TEST_CASE("Lexer: second-line token position") {
    auto toks = lex_skip_eof("x\ny");
    REQUIRE(toks.size() == 2);
    CHECK(toks[1].line == 2);
    CHECK(toks[1].col  == 1);
}

// ── full expression token stream ──────────────────────────────────────────────

TEST_CASE("Lexer: arithmetic expression token stream") {
    auto toks = lex_skip_eof("1 + 2 * 3");
    REQUIRE(toks.size() == 5);
    CHECK(toks[0].type  == TT_INT); CHECK(toks[0].value == "1");
    CHECK(toks[1].type  == TT_PLUS);
    CHECK(toks[2].type  == TT_INT); CHECK(toks[2].value == "2");
    CHECK(toks[3].type  == TT_MUL);
    CHECK(toks[4].type  == TT_INT); CHECK(toks[4].value == "3");
}

TEST_CASE("Lexer: function call token stream") {
    auto toks = lex_skip_eof("write(42)");
    REQUIRE(toks.size() == 4);
    CHECK(toks[0].type  == TT_IDENTIFIER); CHECK(toks[0].value == "write");
    CHECK(toks[1].type  == TT_LPAREN);
    CHECK(toks[2].type  == TT_INT);
    CHECK(toks[3].type  == TT_RPAREN);
}

// ── EOF sentinel ──────────────────────────────────────────────────────────────

TEST_CASE("Lexer: always ends with EOF") {
    auto toks = luz::lex("x = 1");
    REQUIRE_FALSE(toks.empty());
    CHECK(toks.back().type == TT_EOF);
}

TEST_CASE("Lexer: empty source is just EOF") {
    auto toks = luz::lex("");
    REQUIRE(toks.size() == 1);
    CHECK(toks[0].type == TT_EOF);
}
