#include "luz/ast_printer.hpp"

#include <string>

namespace luz {
namespace {

const char* bin_op_symbol(BinOp op) {
    switch (op) {
        case BinOp::Add:      return "+";
        case BinOp::Sub:      return "-";
        case BinOp::Mul:      return "*";
        case BinOp::Div:      return "/";
        case BinOp::FloorDiv: return "//";
        case BinOp::Mod:      return "%";
        case BinOp::Pow:      return "**";
        case BinOp::Eq:       return "==";
        case BinOp::Ne:       return "!=";
        case BinOp::Lt:       return "<";
        case BinOp::Gt:       return ">";
        case BinOp::Le:       return "<=";
        case BinOp::Ge:       return ">=";
        case BinOp::And:      return "and";
        case BinOp::Or:       return "or";
    }
    return "?";
}

const char* un_op_symbol(UnOp op) {
    switch (op) {
        case UnOp::Neg: return "-";
        case UnOp::Not: return "not";
    }
    return "?";
}

void print_indent(std::ostream& os, int indent) {
    for (int i = 0; i < indent; ++i) os.put(' ');
}

void print_expr(std::ostream& os, const Expr& expr, int indent) {
    print_indent(os, indent);
    switch (expr.kind) {
        case NodeKind::IntLit:
            os << "Int(" << static_cast<const IntLit&>(expr).value << ")\n";
            break;
        case NodeKind::FloatLit:
            os << "Float(" << static_cast<const FloatLit&>(expr).value << ")\n";
            break;
        case NodeKind::StringLit:
            os << "String(\"" << static_cast<const StringLit&>(expr).value << "\")\n";
            break;
        case NodeKind::BoolLit:
            os << "Bool(" << (static_cast<const BoolLit&>(expr).value ? "true" : "false") << ")\n";
            break;
        case NodeKind::NullLit:
            os << "Null\n";
            break;
        case NodeKind::Identifier:
            os << "Ident(" << static_cast<const Identifier&>(expr).name << ")\n";
            break;
        case NodeKind::UnaryOp: {
            const auto& n = static_cast<const UnaryOp&>(expr);
            os << "Unary(" << un_op_symbol(n.op) << ")\n";
            print_expr(os, *n.operand, indent + 2);
            break;
        }
        case NodeKind::BinaryOp: {
            const auto& n = static_cast<const BinaryOp&>(expr);
            os << "Binary(" << bin_op_symbol(n.op) << ")\n";
            print_expr(os, *n.lhs, indent + 2);
            print_expr(os, *n.rhs, indent + 2);
            break;
        }
        case NodeKind::Call: {
            const auto& n = static_cast<const Call&>(expr);
            os << "Call\n";
            print_indent(os, indent + 2); os << "callee:\n";
            print_expr(os, *n.callee, indent + 4);
            print_indent(os, indent + 2); os << "args:\n";
            for (const auto& a : n.args) {
                print_expr(os, *a, indent + 4);
            }
            break;
        }
    }
}

}  // namespace

void print_ast(std::ostream& os, const Program& program) {
    os << "Program\n";
    for (const auto& stmt : program.statements) {
        print_expr(os, *stmt, 2);
    }
}

}  // namespace luz
