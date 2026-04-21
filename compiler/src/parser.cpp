#include "luz/parser.hpp"

#include <cstdlib>
#include <initializer_list>
#include <string>
#include <utility>

#include "luz/diagnostics.hpp"
#include "luz/lexer.hpp"

namespace luz {
namespace {

class Parser {
public:
    explicit Parser(const std::vector<Token>& tokens) : tokens_(tokens) {}

    Program parse_program() {
        Program p;
        p.statements = block_body();
        return p;
    }

private:
    const std::vector<Token>& tokens_;
    std::size_t               pos_ = 0;

    // ── Token access ─────────────────────────────────────────────────────────
    const Token& peek(std::size_t offset = 0) const {
        std::size_t idx = pos_ + offset;
        if (idx >= tokens_.size()) return tokens_.back();
        return tokens_[idx];
    }
    bool at_end() const { return peek().type == TT_EOF; }

    const Token& advance() {
        const Token& t = tokens_[pos_];
        if (!at_end()) ++pos_;
        return t;
    }

    bool check(TokenType t) const { return peek().type == t; }

    bool match(TokenType t) {
        if (check(t)) { advance(); return true; }
        return false;
    }

    const Token& expect(TokenType t, const char* what) {
        if (!check(t)) {
            const Token& tok = peek();
            throw ParseError(
                std::string("expected ") + what + ", got " + token_type_name(tok.type),
                tok.line, tok.col);
        }
        return advance();
    }

    SourcePos pos_of(const Token& t) const { return {t.line, t.col}; }

    bool is_one_of(TokenType t, std::initializer_list<TokenType> ops) const {
        for (TokenType c : ops) { if (t == c) return true; }
        return false;
    }

    // ── Type name parsing ─────────────────────────────────────────────────────
    // Parses: TypeName  or  TypeName[TypeArg, ...]  or  TypeName?
    std::string parse_type_name() {
        if (!check(TT_IDENTIFIER) && !check(TT_NULL)) {
            throw ParseError("expected type name", peek().line, peek().col);
        }
        std::string t = peek().value.empty()
            ? std::string(token_type_name(peek().type))
            : peek().value;
        advance();
        if (match(TT_LBRACKET)) {
            t += '[';
            t += parse_type_name();
            while (match(TT_COMMA)) { t += ','; t += parse_type_name(); }
            expect(TT_RBRACKET, "']'");
            t += ']';
        }
        if (match(TT_QUESTION)) t += '?';
        return t;
    }

    // ── Block body ────────────────────────────────────────────────────────────
    // Parses zero or more statements until EOF or '}'.
    Block block_body() {
        Block stmts;
        while (!at_end() && !check(TT_RBRACE)) {
            stmts.push_back(statement());
        }
        return stmts;
    }

    // Consumes '{' stmts '}' and returns the body.
    Block braced_block(const char* context) {
        expect(TT_LBRACE, (std::string("'{'") + " after " + context).c_str());
        Block body = block_body();
        expect(TT_RBRACE, "'}'");
        return body;
    }

    // ── Statement dispatch ────────────────────────────────────────────────────
    StmtPtr statement() {
        const Token& t = peek();
        switch (t.type) {
            case TT_IF:       return stmt_if();
            case TT_WHILE:    return stmt_while();
            case TT_FOR:      return stmt_for();
            case TT_FUNCTION: return stmt_func_def();
            case TT_RETURN:   return stmt_return();
            case TT_BREAK:    advance(); return StmtPtr(new Break(pos_of(t)));
            case TT_CONTINUE: advance(); return StmtPtr(new Continue(pos_of(t)));
            case TT_PASS:     advance(); return StmtPtr(new Pass(pos_of(t)));
            case TT_CONST:    return stmt_const();
            case TT_STRUCT:   return stmt_struct();
            case TT_CLASS:    return stmt_class();
            case TT_IMPORT:   return stmt_import();
            case TT_FROM:     return stmt_from_import();
            case TT_ATTEMPT:  return stmt_attempt();
            case TT_ALERT:    return stmt_alert();
            case TT_SWITCH:   return stmt_switch();
            case TT_IDENTIFIER: return stmt_starting_with_ident();
            default:          return stmt_expr();
        }
    }

    // ── if / elif / else ─────────────────────────────────────────────────────
    StmtPtr stmt_if() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'if'
        std::unique_ptr<If> node(new If(p));

        {
            IfBranch branch;
            branch.condition = expression();
            branch.body      = braced_block("if condition");
            node->branches.push_back(std::move(branch));
        }

        while (check(TT_ELIF)) {
            advance();  // consume 'elif'
            IfBranch branch;
            branch.condition = expression();
            branch.body      = braced_block("elif condition");
            node->branches.push_back(std::move(branch));
        }

        if (match(TT_ELSE)) {
            node->else_body = braced_block("else");
        }

        return StmtPtr(std::move(node));
    }

    // ── while ─────────────────────────────────────────────────────────────────
    StmtPtr stmt_while() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'while'
        ExprPtr cond = expression();
        Block   body = braced_block("while condition");
        return StmtPtr(new While(std::move(cond), std::move(body), p));
    }

    // ── for ──────────────────────────────────────────────────────────────────
    // Two forms:
    //   for i = start to end { ... }       (numeric range)
    //   for x in iterable { ... }          (for-each)
    StmtPtr stmt_for() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'for'

        if (!check(TT_IDENTIFIER)) {
            throw ParseError("expected variable name after 'for'", peek().line, peek().col);
        }
        std::string var = peek().value;
        advance();

        // for x in iterable
        if (match(TT_IN)) {
            ExprPtr iterable = expression();
            Block   body     = braced_block("for-each");
            return StmtPtr(new ForEach(var, std::move(iterable), std::move(body), p));
        }

        // for i = start to end [step n]
        expect(TT_ASSIGN, "'=' or 'in' after loop variable");
        ExprPtr start = expression();
        expect(TT_TO, "'to'");
        ExprPtr end = expression();

        ExprPtr step;
        if (match(TT_STEP)) {
            step = expression();
        }

        Block body = braced_block("for range");
        return StmtPtr(new For(var, std::move(start), std::move(end), std::move(step), std::move(body), p));
    }

    // ── function ─────────────────────────────────────────────────────────────
    StmtPtr stmt_func_def() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'function'

        const Token& name_tok = expect(TT_IDENTIFIER, "function name");
        std::string name = name_tok.value;

        expect(TT_LPAREN, "'('");

        std::vector<Param> params;
        if (!check(TT_RPAREN)) {
            params.push_back(parse_param());
            while (match(TT_COMMA)) {
                params.push_back(parse_param());
                if (params.back().variadic) break;
            }
        }
        expect(TT_RPAREN, "')'");

        std::string return_type;
        if (match(TT_ARROW)) {
            return_type = parse_type_name();
        }

        Block body = braced_block("function body");
        return StmtPtr(new FuncDef(name, std::move(params), return_type, std::move(body), p));
    }

    Param parse_param() {
        Param prm;
        if (match(TT_ELLIPSIS)) {
            prm.variadic = true;
            if (!check(TT_IDENTIFIER) && !check(TT_SELF)) {
                throw ParseError("expected param name after '...'", peek().line, peek().col);
            }
        }
        if (check(TT_SELF)) {
            prm.name = "self";
            advance();
        } else {
            const Token& t = expect(TT_IDENTIFIER, "parameter name");
            prm.name = t.value;
        }
        if (match(TT_COLON)) {
            prm.type_name = parse_type_name();
        }
        if (match(TT_ASSIGN)) {
            prm.default_val = expression();
        }
        return prm;
    }

    // ── attempt / rescue / finally ───────────────────────────────────────────
    StmtPtr stmt_attempt() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'attempt'
        Block try_body = braced_block("attempt");

        expect(TT_RESCUE, "'rescue'");

        std::string error_var;
        if (match(TT_LPAREN)) {
            const Token& ev = expect(TT_IDENTIFIER, "error variable name");
            error_var = ev.value;
            expect(TT_RPAREN, "')'");
        }

        Block catch_body = braced_block("rescue");

        Block finally_body;
        if (match(TT_FINALLY)) {
            finally_body = braced_block("finally");
        }

        return StmtPtr(new Attempt(
            std::move(try_body), error_var,
            std::move(catch_body), std::move(finally_body), p));
    }

    // ── alert ─────────────────────────────────────────────────────────────────
    StmtPtr stmt_alert() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'alert'
        ExprPtr e = expression();
        return StmtPtr(new Alert(std::move(e), p));
    }

    // ── switch ────────────────────────────────────────────────────────────────
    // switch expr {
    //     case v1, v2 { block }
    //     else        { block }
    // }
    StmtPtr stmt_switch() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'switch'
        ExprPtr subject = expression();

        expect(TT_LBRACE, "'{'");

        std::vector<SwitchCase> cases;
        Block else_body;

        while (!check(TT_RBRACE) && !at_end()) {
            if (match(TT_ELSE)) {
                else_body = braced_block("else");
                break;  // else must be last
            }
            expect(TT_CASE, "'case'");
            SwitchCase sc;
            sc.values.push_back(expression());
            while (match(TT_COMMA)) sc.values.push_back(expression());
            sc.body = braced_block("case");
            cases.push_back(std::move(sc));
        }

        expect(TT_RBRACE, "'}'");
        return StmtPtr(new Switch(
            std::move(subject), std::move(cases), std::move(else_body), p));
    }

    // ── match (expression) ────────────────────────────────────────────────────
    // match expr {
    //     v1, v2 => result
    //     _      => result
    // }
    ExprPtr expr_match() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'match'
        ExprPtr subject = expression();

        expect(TT_LBRACE, "'{'");

        std::vector<MatchArm> arms;
        while (!check(TT_RBRACE) && !at_end()) {
            MatchArm arm;

            // Wildcard: _ => expr
            if (check(TT_IDENTIFIER) && peek().value == "_") {
                advance();
                expect(TT_ARROW, "'=>'");
                arm.result = expression();
                arms.push_back(std::move(arm));
                break;  // wildcard must be last
            }

            // Normal patterns: expr, expr => result
            arm.patterns.push_back(expression());
            while (match(TT_COMMA)) arm.patterns.push_back(expression());
            expect(TT_ARROW, "'=>'");
            arm.result = expression();
            arms.push_back(std::move(arm));
        }

        expect(TT_RBRACE, "'}'");
        return ExprPtr(new Match(std::move(subject), std::move(arms), p));
    }

    // ── lambda / anonymous function ──────────────────────────────────────────
    // fn(params) => expr       short form (implicit return)
    // fn(params) { body }      long form  (block body)
    ExprPtr expr_lambda() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'fn'
        expect(TT_LPAREN, "'(' after 'fn'");

        std::vector<Param> params;
        if (!check(TT_RPAREN)) {
            do {
                Param pm;
                pm.variadic = match(TT_MUL);
                pm.name = expect(TT_IDENTIFIER, "parameter name").value;
                if (match(TT_COLON)) pm.type_name = parse_type_name();
                if (match(TT_ASSIGN)) pm.default_val = expression();
                params.push_back(std::move(pm));
            } while (match(TT_COMMA) && !check(TT_RPAREN));
        }
        expect(TT_RPAREN, "')'");

        if (match(TT_ARROW)) {
            // Short form: fn(x) => expr
            ExprPtr body = expression();
            Block empty;
            return ExprPtr(new Lambda(std::move(params), std::move(body), std::move(empty), p));
        }

        if (check(TT_LBRACE)) {
            // Long form: fn(x) { body }
            Block body = braced_block("fn parameters");
            return ExprPtr(new Lambda(std::move(params), ExprPtr(), std::move(body), p));
        }

        throw ParseError("expected '=>' or '{' after lambda parameters", peek().line, peek().col);
    }

    // ── f-string ─────────────────────────────────────────────────────────────
    // The lexer has already stripped the $"..." delimiters and stored the raw
    // template in the token value, e.g. "Hello {name}, count={1+2}".
    // We scan it character-by-character: plain text goes into Text parts,
    // {expr} regions are re-lexed and re-parsed into Expr parts.
    ExprPtr parse_fstring(const Token& tok) {
        const std::string& raw = tok.value;
        std::vector<FStringPart> parts;
        std::size_t i = 0;

        while (i < raw.size()) {
            if (raw[i] == '{') {
                // Find matching '}', tracking nesting depth.
                int depth = 1;
                std::size_t j = i + 1;
                while (j < raw.size() && depth > 0) {
                    if (raw[j] == '{') ++depth;
                    else if (raw[j] == '}') --depth;
                    ++j;
                }
                // raw[i+1 .. j-2] is the expression text.
                std::string expr_src = raw.substr(i + 1, j - i - 2);
                auto sub_tokens = lex(expr_src);
                // Re-parse as a single expression using a nested Parser.
                Parser sub(sub_tokens);
                ExprPtr e = sub.expression();
                parts.push_back(FStringPart::make_expr(std::move(e)));
                i = j;
            } else {
                // Collect literal text up to the next '{'.
                std::size_t j = i;
                while (j < raw.size() && raw[j] != '{') ++j;
                parts.push_back(FStringPart::make_text(raw.substr(i, j - i)));
                i = j;
            }
        }

        return ExprPtr(new FStringLit(std::move(parts), pos_of(tok)));
    }

    // ── import ────────────────────────────────────────────────────────────────
    // import "path"
    // import "path" as alias
    StmtPtr stmt_import() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'import'
        const Token& path_tok = expect(TT_STRING, "module path string");
        std::string path = path_tok.value;

        std::string alias;
        if (match(TT_AS)) {
            const Token& a = expect(TT_IDENTIFIER, "alias name");
            alias = a.value;
        }

        return StmtPtr(new Import(path, alias, {}, p));
    }

    // from "path" import name, name2, ...
    StmtPtr stmt_from_import() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'from'
        const Token& path_tok = expect(TT_STRING, "module path string");
        std::string path = path_tok.value;

        expect(TT_IMPORT, "'import'");

        std::vector<std::string> names;
        const Token& first = expect(TT_IDENTIFIER, "name to import");
        names.push_back(first.value);
        while (match(TT_COMMA)) {
            const Token& n = expect(TT_IDENTIFIER, "name to import");
            names.push_back(n.value);
        }

        return StmtPtr(new Import(path, {}, std::move(names), p));
    }

    // ── struct ────────────────────────────────────────────────────────────────
    // struct Name { field: Type [= default], ... }
    StmtPtr stmt_struct() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'struct'

        const Token& name_tok = expect(TT_IDENTIFIER, "struct name");
        std::string name = name_tok.value;

        expect(TT_LBRACE, "'{'");

        std::vector<StructField> fields;
        while (!check(TT_RBRACE) && !at_end()) {
            const Token& fname = expect(TT_IDENTIFIER, "field name");
            expect(TT_COLON, "':'");
            std::string type_name = parse_type_name();

            ExprPtr def_val;
            if (match(TT_ASSIGN)) {
                def_val = expression();
            }

            StructField f;
            f.name        = fname.value;
            f.type_name   = type_name;
            f.default_val = std::move(def_val);
            fields.push_back(std::move(f));

            match(TT_COMMA);  // optional separator between fields
        }

        expect(TT_RBRACE, "'}'");
        return StmtPtr(new StructDef(name, std::move(fields), p));
    }

    // ── class ─────────────────────────────────────────────────────────────────
    // class Name [extends Parent] { function method(...) { ... } ... }
    StmtPtr stmt_class() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'class'

        const Token& name_tok = expect(TT_IDENTIFIER, "class name");
        std::string name = name_tok.value;

        std::string parent;
        if (match(TT_EXTENDS)) {
            const Token& ptok = expect(TT_IDENTIFIER, "parent class name");
            parent = ptok.value;
        }

        expect(TT_LBRACE, "'{'");

        std::vector<StmtPtr> methods;
        while (!check(TT_RBRACE) && !at_end()) {
            if (!check(TT_FUNCTION)) {
                throw ParseError(
                    "expected 'function' inside class body",
                    peek().line, peek().col);
            }
            methods.push_back(stmt_func_def());
        }

        expect(TT_RBRACE, "'}'");
        return StmtPtr(new ClassDef(name, parent, std::move(methods), p));
    }

    // ── return ────────────────────────────────────────────────────────────────
    StmtPtr stmt_return() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'return'
        ExprPtr val;
        // Only consume an expression if the next token can start one.
        if (!at_end() && !check(TT_RBRACE)) {
            val = expression();
        }
        return StmtPtr(new Return(std::move(val), p));
    }

    // ── const ─────────────────────────────────────────────────────────────────
    StmtPtr stmt_const() {
        SourcePos p = pos_of(peek());
        advance();  // consume 'const'

        const Token& name_tok = expect(TT_IDENTIFIER, "constant name");
        std::string name = name_tok.value;

        std::string type_name;
        if (match(TT_COLON)) {
            type_name = parse_type_name();
        }

        expect(TT_ASSIGN, "'='");
        ExprPtr val = expression();
        return StmtPtr(new ConstDecl(name, type_name, std::move(val), p));
    }

    // ── identifier-led statements ─────────────────────────────────────────────
    // Distinguishes between:
    //   x = expr           plain assignment / new binding
    //   x: type = expr     typed assignment
    //   anything else      expression statement (call, etc.)
    StmtPtr stmt_starting_with_ident() {
        SourcePos p = pos_of(peek());
        const std::string name = peek().value;

        // x: type = expr
        if (peek(1).type == TT_COLON) {
            // Scan past type annotation to find '='.
            std::size_t saved = pos_;
            advance();  // consume identifier
            advance();  // consume ':'
            std::string type_name;
            try { type_name = parse_type_name(); }
            catch (...) { pos_ = saved; return stmt_expr(); }

            if (!check(TT_ASSIGN)) {
                pos_ = saved;
                return stmt_expr();
            }
            advance();  // consume '='
            ExprPtr val = expression();
            return StmtPtr(new TypedAssign(name, type_name, std::move(val), p));
        }

        // x = expr
        if (peek(1).type == TT_ASSIGN) {
            advance();  // consume identifier
            advance();  // consume '='
            ExprPtr val = expression();
            return StmtPtr(new Assign(name, std::move(val), p));
        }

        // x += expr  (and other compound operators) — desugar to Assign
        if (is_one_of(peek(1).type, {TT_PLUS_ASSIGN, TT_MINUS_ASSIGN,
                                      TT_MUL_ASSIGN, TT_DIV_ASSIGN,
                                      TT_MOD_ASSIGN, TT_POW_ASSIGN})) {
            advance();  // consume identifier
            TokenType compound = peek().type;
            SourcePos op_pos   = pos_of(peek());
            advance();  // consume operator
            ExprPtr rhs = expression();

            BinOp bop;
            switch (compound) {
                case TT_PLUS_ASSIGN:  bop = BinOp::Add;      break;
                case TT_MINUS_ASSIGN: bop = BinOp::Sub;      break;
                case TT_MUL_ASSIGN:   bop = BinOp::Mul;      break;
                case TT_DIV_ASSIGN:   bop = BinOp::Div;      break;
                case TT_MOD_ASSIGN:   bop = BinOp::Mod;      break;
                case TT_POW_ASSIGN:   bop = BinOp::Pow;      break;
                default:              bop = BinOp::Add;      break;
            }
            ExprPtr lhs(new Identifier(name, p));
            ExprPtr combined(new BinaryOp(bop, std::move(lhs), std::move(rhs), op_pos));
            return StmtPtr(new Assign(name, std::move(combined), p));
        }

        return stmt_expr();
    }

    // ── expression statement ─────────────────────────────────────────────────
    // Also handles attribute assignment (obj.x = val) and index assignment
    // (arr[i] = val) which are only detectable after parsing the lhs expression.
    StmtPtr stmt_expr() {
        SourcePos p = pos_of(peek());
        ExprPtr e = expression();

        if (check(TT_ASSIGN)) {
            advance();  // consume '='
            ExprPtr val = expression();

            if (e->kind == NodeKind::Attribute) {
                auto* attr = static_cast<Attribute*>(e.get());
                return StmtPtr(new AttrAssign(
                    std::move(attr->object), attr->name, std::move(val), p));
            }
            if (e->kind == NodeKind::IndexAccess) {
                auto* ia = static_cast<IndexAccess*>(e.get());
                return StmtPtr(new IndexAssign(
                    std::move(ia->base), std::move(ia->index), std::move(val), p));
            }
            // Any other lhs (e.g. bare identifier) is a plain assignment.
            // Extract the name if it's an identifier, otherwise emit ExprStmt
            // and let the typechecker reject it.
            if (e->kind == NodeKind::Identifier) {
                auto* id = static_cast<Identifier*>(e.get());
                return StmtPtr(new Assign(id->name, std::move(val), p));
            }
        }

        return StmtPtr(new ExprStmt(std::move(e), p));
    }

    // ── Expression parsing (same precedence ladder as before) ────────────────
    ExprPtr expression()       { return logical_or(); }

    ExprPtr logical_or() {
        ExprPtr lhs = logical_and();
        while (check(TT_OR)) {
            const Token& op = advance();
            ExprPtr rhs = logical_and();
            lhs.reset(new BinaryOp(BinOp::Or, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    ExprPtr logical_and() {
        ExprPtr lhs = logical_not();
        while (check(TT_AND)) {
            const Token& op = advance();
            ExprPtr rhs = logical_not();
            lhs.reset(new BinaryOp(BinOp::And, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    ExprPtr logical_not() {
        if (check(TT_NOT)) {
            const Token& op = advance();
            return ExprPtr(new UnaryOp(UnOp::Not, logical_not(), pos_of(op)));
        }
        return comparison();
    }

    ExprPtr comparison() {
        ExprPtr lhs = additive();
        while (is_one_of(peek().type, {TT_EE,TT_NE,TT_LT,TT_GT,TT_LTE,TT_GTE})) {
            const Token& op = advance();
            BinOp bop;
            switch (op.type) {
                case TT_EE:  bop = BinOp::Eq; break;
                case TT_NE:  bop = BinOp::Ne; break;
                case TT_LT:  bop = BinOp::Lt; break;
                case TT_GT:  bop = BinOp::Gt; break;
                case TT_LTE: bop = BinOp::Le; break;
                case TT_GTE: bop = BinOp::Ge; break;
                default:     bop = BinOp::Eq; break;
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

    ExprPtr power() {
        ExprPtr lhs = unary();
        if (check(TT_POW)) {
            const Token& op = advance();
            ExprPtr rhs = power();
            return ExprPtr(new BinaryOp(BinOp::Pow, std::move(lhs), std::move(rhs), pos_of(op)));
        }
        return lhs;
    }

    ExprPtr unary() {
        if (check(TT_MINUS)) {
            const Token& op = advance();
            return ExprPtr(new UnaryOp(UnOp::Neg, unary(), pos_of(op)));
        }
        return call();
    }

    // Postfix chain: calls f(...), index [i], attribute .name — left-to-right.
    ExprPtr call() {
        ExprPtr expr = primary();
        for (;;) {
            if (check(TT_LPAREN)) {
                const Token& lparen = advance();
                std::vector<ExprPtr> args;
                if (!check(TT_RPAREN)) {
                    args.push_back(expression());
                    while (match(TT_COMMA)) args.push_back(expression());
                }
                expect(TT_RPAREN, "')'");
                expr.reset(new Call(std::move(expr), std::move(args), pos_of(lparen)));
            } else if (check(TT_LBRACKET)) {
                const Token& lb = advance();
                ExprPtr idx = expression();
                expect(TT_RBRACKET, "']'");
                expr.reset(new IndexAccess(std::move(expr), std::move(idx), pos_of(lb)));
            } else if (check(TT_DOT)) {
                const Token& dot = advance();
                const Token& attr = expect(TT_IDENTIFIER, "attribute name");
                expr.reset(new Attribute(std::move(expr), attr.value, pos_of(dot)));
            } else {
                break;
            }
        }
        return expr;
    }

    ExprPtr primary() {
        const Token& t = peek();
        switch (t.type) {
            case TT_INT:
                advance();
                return ExprPtr(new IntLit(std::strtoll(t.value.c_str(), nullptr, 10), pos_of(t)));
            case TT_FLOAT:
                advance();
                return ExprPtr(new FloatLit(std::strtod(t.value.c_str(), nullptr), pos_of(t)));
            case TT_STRING:
                advance();
                return ExprPtr(new StringLit(t.value, pos_of(t)));
            case TT_FSTRING:
                advance();
                return parse_fstring(t);
            case TT_MATCH:
                return expr_match();
            case TT_TRUE:
                advance();
                return ExprPtr(new BoolLit(true, pos_of(t)));
            case TT_FALSE:
                advance();
                return ExprPtr(new BoolLit(false, pos_of(t)));
            case TT_NULL:
                advance();
                return ExprPtr(new NullLit(pos_of(t)));
            case TT_IDENTIFIER:
                advance();
                return ExprPtr(new Identifier(t.value, pos_of(t)));
            case TT_SELF:
                advance();
                return ExprPtr(new Identifier("self", pos_of(t)));
            case TT_LPAREN: {
                advance();
                ExprPtr inner = expression();
                expect(TT_RPAREN, "')'");
                return inner;
            }
            case TT_LBRACKET: {
                // List literal: [expr, ...]
                SourcePos lp = pos_of(t);
                advance();
                std::vector<ExprPtr> elems;
                if (!check(TT_RBRACKET)) {
                    elems.push_back(expression());
                    while (match(TT_COMMA) && !check(TT_RBRACKET))
                        elems.push_back(expression());
                }
                expect(TT_RBRACKET, "']'");
                return ExprPtr(new ListLit(std::move(elems), lp));
            }
            case TT_LBRACE: {
                // Dict literal: {key: value, ...}
                SourcePos lp = pos_of(t);
                advance();
                std::vector<DictPair> pairs;
                if (!check(TT_RBRACE)) {
                    do {
                        ExprPtr k = expression();
                        expect(TT_COLON, "':'");
                        ExprPtr v = expression();
                        DictPair dp;
                        dp.key   = std::move(k);
                        dp.value = std::move(v);
                        pairs.push_back(std::move(dp));
                    } while (match(TT_COMMA) && !check(TT_RBRACE));
                }
                expect(TT_RBRACE, "'}'");
                return ExprPtr(new DictLit(std::move(pairs), lp));
            }
            case TT_FN:
                return expr_lambda();
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
