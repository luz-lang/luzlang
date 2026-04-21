#include "luz/ast_printer.hpp"

namespace luz {
namespace {

void print_indent(std::ostream& os, int n) {
    for (int i = 0; i < n; ++i) os.put(' ');
}

void print_expr(std::ostream& os, const Expr& e, int ind);
void print_stmt(std::ostream& os, const Stmt& s, int ind);
void print_block(std::ostream& os, const Block& b, int ind);

const char* bin_op_sym(BinOp op) {
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

void print_expr(std::ostream& os, const Expr& e, int ind) {
    print_indent(os, ind);
    switch (e.kind) {
        case NodeKind::IntLit:
            os << "Int(" << static_cast<const IntLit&>(e).value << ")\n";
            break;
        case NodeKind::FloatLit:
            os << "Float(" << static_cast<const FloatLit&>(e).value << ")\n";
            break;
        case NodeKind::StringLit:
            os << "Str(\"" << static_cast<const StringLit&>(e).value << "\")\n";
            break;
        case NodeKind::BoolLit:
            os << "Bool(" << (static_cast<const BoolLit&>(e).value ? "true" : "false") << ")\n";
            break;
        case NodeKind::NullLit:
            os << "Null\n";
            break;
        case NodeKind::Identifier:
            os << "Ident(" << static_cast<const Identifier&>(e).name << ")\n";
            break;
        case NodeKind::UnaryOp: {
            const auto& n = static_cast<const UnaryOp&>(e);
            os << "Unary(" << (n.op == UnOp::Neg ? "-" : "not") << ")\n";
            print_expr(os, *n.operand, ind + 2);
            break;
        }
        case NodeKind::BinaryOp: {
            const auto& n = static_cast<const BinaryOp&>(e);
            os << "Binary(" << bin_op_sym(n.op) << ")\n";
            print_expr(os, *n.lhs, ind + 2);
            print_expr(os, *n.rhs, ind + 2);
            break;
        }
        case NodeKind::Call: {
            const auto& n = static_cast<const Call&>(e);
            os << "Call\n";
            print_indent(os, ind + 2); os << "callee:\n";
            print_expr(os, *n.callee, ind + 4);
            if (!n.args.empty()) {
                print_indent(os, ind + 2); os << "args:\n";
                for (const auto& a : n.args) print_expr(os, *a, ind + 4);
            }
            break;
        }
        case NodeKind::ListLit: {
            const auto& n = static_cast<const ListLit&>(e);
            os << "List[" << n.elements.size() << "]\n";
            for (const auto& el : n.elements) print_expr(os, *el, ind + 2);
            break;
        }
        case NodeKind::DictLit: {
            const auto& n = static_cast<const DictLit&>(e);
            os << "Dict[" << n.pairs.size() << "]\n";
            for (const auto& p : n.pairs) {
                print_indent(os, ind + 2); os << "key:\n";
                print_expr(os, *p.key, ind + 4);
                print_indent(os, ind + 2); os << "val:\n";
                print_expr(os, *p.value, ind + 4);
            }
            break;
        }
        case NodeKind::IndexAccess: {
            const auto& n = static_cast<const IndexAccess&>(e);
            os << "Index\n";
            print_expr(os, *n.base,  ind + 2);
            print_expr(os, *n.index, ind + 2);
            break;
        }
        case NodeKind::Attribute: {
            const auto& n = static_cast<const Attribute&>(e);
            os << "Attr(." << n.name << ")\n";
            print_expr(os, *n.object, ind + 2);
            break;
        }
        default:
            os << "<?expr>\n";
            break;
    }
}

void print_block(std::ostream& os, const Block& b, int ind) {
    for (const auto& s : b) print_stmt(os, *s, ind);
}

void print_stmt(std::ostream& os, const Stmt& s, int ind) {
    print_indent(os, ind);
    switch (s.kind) {
        case NodeKind::ExprStmt:
            os << "ExprStmt\n";
            print_expr(os, *static_cast<const ExprStmt&>(s).expr, ind + 2);
            break;
        case NodeKind::Assign: {
            const auto& n = static_cast<const Assign&>(s);
            os << "Assign(" << n.name << ")\n";
            print_expr(os, *n.value, ind + 2);
            break;
        }
        case NodeKind::TypedAssign: {
            const auto& n = static_cast<const TypedAssign&>(s);
            os << "TypedAssign(" << n.name << ": " << n.type_name << ")\n";
            print_expr(os, *n.value, ind + 2);
            break;
        }
        case NodeKind::ConstDecl: {
            const auto& n = static_cast<const ConstDecl&>(s);
            os << "Const(" << n.name;
            if (!n.type_name.empty()) os << ": " << n.type_name;
            os << ")\n";
            print_expr(os, *n.value, ind + 2);
            break;
        }
        case NodeKind::If: {
            const auto& n = static_cast<const If&>(s);
            os << "If\n";
            for (std::size_t i = 0; i < n.branches.size(); ++i) {
                print_indent(os, ind + 2);
                os << (i == 0 ? "if" : "elif") << ":\n";
                print_indent(os, ind + 4); os << "cond:\n";
                print_expr(os, *n.branches[i].condition, ind + 6);
                print_indent(os, ind + 4); os << "body:\n";
                print_block(os, n.branches[i].body, ind + 6);
            }
            if (!n.else_body.empty()) {
                print_indent(os, ind + 2); os << "else:\n";
                print_block(os, n.else_body, ind + 4);
            }
            break;
        }
        case NodeKind::While: {
            const auto& n = static_cast<const While&>(s);
            os << "While\n";
            print_indent(os, ind + 2); os << "cond:\n";
            print_expr(os, *n.condition, ind + 4);
            print_indent(os, ind + 2); os << "body:\n";
            print_block(os, n.body, ind + 4);
            break;
        }
        case NodeKind::For: {
            const auto& n = static_cast<const For&>(s);
            os << "For(" << n.var << ")\n";
            print_indent(os, ind + 2); os << "start:\n";
            print_expr(os, *n.start, ind + 4);
            print_indent(os, ind + 2); os << "end:\n";
            print_expr(os, *n.end, ind + 4);
            if (n.step) {
                print_indent(os, ind + 2); os << "step:\n";
                print_expr(os, *n.step, ind + 4);
            }
            print_indent(os, ind + 2); os << "body:\n";
            print_block(os, n.body, ind + 4);
            break;
        }
        case NodeKind::ForEach: {
            const auto& n = static_cast<const ForEach&>(s);
            os << "ForEach(" << n.var << ")\n";
            print_indent(os, ind + 2); os << "in:\n";
            print_expr(os, *n.iterable, ind + 4);
            print_indent(os, ind + 2); os << "body:\n";
            print_block(os, n.body, ind + 4);
            break;
        }
        case NodeKind::Break:
            os << "Break\n"; break;
        case NodeKind::Continue:
            os << "Continue\n"; break;
        case NodeKind::Pass:
            os << "Pass\n"; break;
        case NodeKind::Return: {
            const auto& n = static_cast<const Return&>(s);
            os << "Return\n";
            if (n.value) print_expr(os, *n.value, ind + 2);
            break;
        }
        case NodeKind::FuncDef: {
            const auto& n = static_cast<const FuncDef&>(s);
            os << "FuncDef(" << n.name << ")\n";
            if (!n.params.empty()) {
                print_indent(os, ind + 2); os << "params:";
                for (const auto& p : n.params) {
                    os << " " << p.name;
                    if (!p.type_name.empty()) os << ":" << p.type_name;
                    if (p.variadic) os << "...";
                }
                os << "\n";
            }
            if (!n.return_type.empty()) {
                print_indent(os, ind + 2); os << "-> " << n.return_type << "\n";
            }
            print_indent(os, ind + 2); os << "body:\n";
            print_block(os, n.body, ind + 4);
            break;
        }
        default:
            os << "<?stmt>\n"; break;
    }
}

}  // namespace

void print_ast(std::ostream& os, const Program& program) {
    os << "Program\n";
    print_block(os, program.statements, 2);
}

}  // namespace luz
