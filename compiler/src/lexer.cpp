#include "luz/lexer.hpp"

#include <stdexcept>
#include <string>

namespace luz {

std::vector<Token> lex(const std::string& source) {
    CLexer state{};
    lexer_init(&state, source.c_str());

    int count = 0;
    CToken* raw = lex_all(&state, &count);
    if (raw == nullptr) {
        throw std::runtime_error("lexer: out of memory");
    }

    std::vector<Token> tokens;
    tokens.reserve(static_cast<std::size_t>(count));
    for (int i = 0; i < count; ++i) {
        Token t;
        t.type  = raw[i].type;
        t.line  = raw[i].line;
        t.col   = raw[i].col;
        if (raw[i].value != nullptr) {
            t.value = raw[i].value;
        }
        tokens.push_back(std::move(t));
    }

    free_tokens(raw, count);
    return tokens;
}

const char* token_type_name(TokenType t) noexcept {
    switch (t) {
        case TT_INT:            return "INT";
        case TT_FLOAT:          return "FLOAT";
        case TT_PLUS:           return "PLUS";
        case TT_MINUS:          return "MINUS";
        case TT_MUL:            return "MUL";
        case TT_DIV:            return "DIV";
        case TT_MOD:            return "MOD";
        case TT_POW:            return "POW";
        case TT_IDIV:           return "IDIV";
        case TT_LPAREN:         return "LPAREN";
        case TT_RPAREN:         return "RPAREN";
        case TT_IDENTIFIER:     return "IDENTIFIER";
        case TT_ASSIGN:         return "ASSIGN";
        case TT_EE:             return "EE";
        case TT_NE:             return "NE";
        case TT_LT:             return "LT";
        case TT_GT:             return "GT";
        case TT_LTE:            return "LTE";
        case TT_GTE:            return "GTE";
        case TT_IF:             return "IF";
        case TT_ELIF:           return "ELIF";
        case TT_ELSE:           return "ELSE";
        case TT_WHILE:          return "WHILE";
        case TT_FOR:            return "FOR";
        case TT_TO:             return "TO";
        case TT_IN:             return "IN";
        case TT_TRUE:           return "TRUE";
        case TT_FALSE:          return "FALSE";
        case TT_NULL:           return "NULL";
        case TT_AND:            return "AND";
        case TT_OR:             return "OR";
        case TT_NOT:            return "NOT";
        case TT_FUNCTION:       return "FUNCTION";
        case TT_RETURN:         return "RETURN";
        case TT_FN:             return "FN";
        case TT_ARROW:          return "ARROW";
        case TT_IMPORT:         return "IMPORT";
        case TT_FROM:           return "FROM";
        case TT_AS:             return "AS";
        case TT_ATTEMPT:        return "ATTEMPT";
        case TT_RESCUE:         return "RESCUE";
        case TT_FINALLY:        return "FINALLY";
        case TT_ALERT:          return "ALERT";
        case TT_BREAK:          return "BREAK";
        case TT_CONTINUE:       return "CONTINUE";
        case TT_PASS:           return "PASS";
        case TT_CLASS:          return "CLASS";
        case TT_SELF:           return "SELF";
        case TT_EXTENDS:        return "EXTENDS";
        case TT_DOT:            return "DOT";
        case TT_STRING:         return "STRING";
        case TT_FSTRING:        return "FSTRING";
        case TT_COMMA:          return "COMMA";
        case TT_COLON:          return "COLON";
        case TT_LBRACKET:       return "LBRACKET";
        case TT_RBRACKET:       return "RBRACKET";
        case TT_LBRACE:         return "LBRACE";
        case TT_RBRACE:         return "RBRACE";
        case TT_PLUS_ASSIGN:    return "PLUS_ASSIGN";
        case TT_MINUS_ASSIGN:   return "MINUS_ASSIGN";
        case TT_MUL_ASSIGN:     return "MUL_ASSIGN";
        case TT_DIV_ASSIGN:     return "DIV_ASSIGN";
        case TT_MOD_ASSIGN:     return "MOD_ASSIGN";
        case TT_POW_ASSIGN:     return "POW_ASSIGN";
        case TT_NULL_COALESCE:  return "NULL_COALESCE";
        case TT_NOT_IN:         return "NOT_IN";
        case TT_ELLIPSIS:       return "ELLIPSIS";
        case TT_SWITCH:         return "SWITCH";
        case TT_CASE:           return "CASE";
        case TT_MATCH:          return "MATCH";
        case TT_STEP:           return "STEP";
        case TT_CONST:          return "CONST";
        case TT_STRUCT:         return "STRUCT";
        case TT_QUESTION:       return "QUESTION";
        case TT_EOF:            return "EOF";
        case TT_ERROR:          return "ERROR";
    }
    return "UNKNOWN";
}

}  // namespace luz
