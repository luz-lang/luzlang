#include "luz/parser.hpp"

#include <cstdlib>
#include <initializer_list>
#include <string>
#include <utility>

#include "luz/diagnostics.hpp"

namespace luz {
namespace {

// Recursive-descent parser over a flat token vector. Mirrors the precedence
// ladder of luz/parser.py: or < and < not < comparison < additive <
// multiplicative < power < unary < primary.
class Parser {
public:
    explicit Parser(const std::vector<Token>& tokens) : tokens_(tokens) {}

    Program parse_program() {
        Program p;
        while (!at_end()) {
            p.statements.push_back(expression());
        }
        return p;
    }

private:
    const std::vector<Token>& tokens_;
    std::size_t               pos_ = 0;

    const Token& peek(std::size_t offset = 0) const {
        std::size_t idx = pos_ + offset;
        if (idx >= tokens_.size()) {
            return tokens_.back();  // always TT_EOF
        }
        return tokens_[idx];
    }

    bool at_end() const { return peek().type == TT_EOF; }

    const Token& advance() {
        const Token& t = tokens_[pos_];
        if (!at_end()) {
            ++pos_;
        }
        return t;
    }

    bool match(TokenType t) {
        if (peek().type == t) {
            advance();
            return true;
        }
        return false;
    }

    const Token& expect(TokenType t, const char* what) {
        if (peek().type != t) {
            const Token& tok = peek();
            throw ParseError(
                std::string("expected ") + what + ", got " + token_type_name(tok.type),
                tok.line, tok.col);
        }
        return advance();
    }

    SourcePos pos_of(const Token& t) const { return {t.line, t.col}; }

    bool is_one_of(TokenType t, std::initializer_list<TokenType> ops) const {
        for (TokenType c : ops) {
            if (t == c) return true;
        }
        return false;
    }

    // ── Precedence ladder ─────────────────────────────────────────────────────
    ExprPtr expression()  { return logical_or(); }

    ExprPtr logical_or() {
        ExprPtr lhs = logical_and();
        while (peek().type == TT_OR) {
            const Token& op = advance();
            ExprPtr rhs = logical_and();
            lhs.reset(new BinaryOp(BinOp::Or, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    ExprPtr logical_and() {
        ExprPtr lhs = logical_not();
        while (peek().type == TT_AND) {
            const Token& op = advance();
            ExprPtr rhs = logical_not();
            lhs.reset(new BinaryOp(BinOp::And, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    ExprPtr logical_not() {
        if (peek().type == TT_NOT) {
            const Token& op = advance();
            return ExprPtr(new UnaryOp(UnOp::Not, logical_not(), pos_of(op)));
        }
        return comparison();
    }

    ExprPtr comparison() {
        ExprPtr lhs = additive();
        while (is_one_of(peek().type, {TT_EE, TT_NE, TT_LT, TT_GT, TT_LTE, TT_GTE})) {
            const Token& op = advance();
            BinOp bop;
            switch (op.type) {
                case TT_EE:  bop = BinOp::Eq; break;
                case TT_NE:  bop = BinOp::Ne; break;
                case TT_LT:  bop = BinOp::Lt; break;
                case TT_GT:  bop = BinOp::Gt; break;
                case TT_LTE: bop = BinOp::Le; break;
                case TT_GTE: bop = BinOp::Ge; break;
                default:     bop = BinOp::Eq; break;  // unreachable
            }
            ExprPtr rhs = additive();
            lhs.reset(new BinaryOp(bop, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    ExprPtr additive() {
        ExprPtr lhs = multiplicative();
        while (is_one_of(peek().type, {TT_PLUS, TT_MINUS})) {
            const Token& op = advance();
            BinOp bop = (op.type == TT_PLUS) ? BinOp::Add : BinOp::Sub;
            ExprPtr rhs = multiplicative();
            lhs.reset(new BinaryOp(bop, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    ExprPtr multiplicative() {
        ExprPtr lhs = power();
        while (is_one_of(peek().type, {TT_MUL, TT_DIV, TT_IDIV, TT_MOD})) {
            const Token& op = advance();
            BinOp bop;
            switch (op.type) {
                case TT_MUL:  bop = BinOp::Mul;      break;
                case TT_DIV:  bop = BinOp::Div;      break;
                case TT_IDIV: bop = BinOp::FloorDiv; break;
                case TT_MOD:  bop = BinOp::Mod;      break;
                default:      bop = BinOp::Mul;      break;
            }
            ExprPtr rhs = power();
            lhs.reset(new BinaryOp(bop, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    // Right-associative: a ** b ** c = a ** (b ** c).
    ExprPtr power() {
        ExprPtr lhs = unary();
        if (peek().type == TT_POW) {
            const Token& op = advance();
            ExprPtr rhs = power();
            return ExprPtr(new BinaryOp(BinOp::Pow, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    ExprPtr unary() {
        if (peek().type == TT_MINUS) {
            const Token& op = advance();
            return ExprPtr(new UnaryOp(UnOp::Neg, unary(), pos_of(op)));
        }
        return call();
    }

    // call = primary ( "(" args ")" )*
    ExprPtr call() {
        ExprPtr expr = primary();
        while (peek().type == TT_LPAREN) {
            const Token& lparen = advance();
            std::vector<ExprPtr> args;
            if (peek().type != TT_RPAREN) {
                args.push_back(expression());
                while (match(TT_COMMA)) {
                    args.push_back(expression());
                }
            }
            expect(TT_RPAREN, "')'");
            expr.reset(new Call(std::move(expr), std::move(args), pos_of(lparen)));
        }
        return expr;
    }

    ExprPtr primary() {
        const Token& t = peek();
        switch (t.type) {
            case TT_INT: {
                advance();
                return ExprPtr(new IntLit(std::strtoll(t.value.c_str(), nullptr, 10), pos_of(t)));
            }
            case TT_FLOAT: {
                advance();
                return ExprPtr(new FloatLit(std::strtod(t.value.c_str(), nullptr), pos_of(t)));
            }
            case TT_STRING: {
                advance();
                return ExprPtr(new StringLit(t.value, pos_of(t)));
            }
            case TT_TRUE:
                advance();
                return ExprPtr(new BoolLit(true, pos_of(t)));
            case TT_FALSE:
                advance();
                return ExprPtr(new BoolLit(false, pos_of(t)));
            case TT_NULL:
                advance();
                return ExprPtr(new NullLit(pos_of(t)));
            case TT_IDENTIFIER: {
                advance();
                return ExprPtr(new Identifier(t.value, pos_of(t)));
            }
            case TT_LPAREN: {
                advance();
                ExprPtr inner = expression();
                expect(TT_RPAREN, "')'");
                return inner;
            }
            default:
                throw ParseError(
                    std::string("unexpected token ") + token_type_name(t.type),
                    t.line, t.col);
        }
    }
};

}  // namespace

Program parse(const std::vector<Token>& tokens) {
    Parser p(tokens);
    return p.parse_program();
}

}  // namespace luz
