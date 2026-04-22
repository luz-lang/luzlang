// typechecker.cpp — Luz compile-time type analysis pass (C++ port).
//
// Mirrors luz/typechecker.py in behaviour:
//   - Infers the type of every literal and annotated variable.
//   - Verifies typed variable declarations match the assigned value.
//   - Records function signatures (param types + return type).
//   - Verifies argument count and types at call sites.
//   - Verifies return statements match the declared return type.
//   - Flags arithmetic on incompatible types (e.g. string + int).
//   - Detects unused variables, parameters, and imports (Go-style errors).
//     Names prefixed with '_' are exempt from unused checks.
//
// Collects ALL errors rather than stopping at the first.

#include "luz/typechecker.hpp"

#include <algorithm>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace luz {

// ─── Type string constants ────────────────────────────────────────────────────

static const std::string kUnknown  = "unknown";
static const std::string kInt      = "int";
static const std::string kFloat    = "float";
static const std::string kNumber   = "number";
static const std::string kString   = "string";
static const std::string kBool     = "bool";
static const std::string kNull     = "null";
static const std::string kList     = "list";
static const std::string kDict     = "dict";
static const std::string kFunction = "function";

static const std::unordered_set<std::string> kFixedInts = {
    "int8","int16","int32","int64","uint8","uint16","uint32","uint64"
};
static const std::unordered_set<std::string> kFixedFloats = {"float32","float64"};
static const std::unordered_set<std::string> kNumeric = {
    "int","float","number",
    "int8","int16","int32","int64",
    "uint8","uint16","uint32","uint64",
    "float32","float64"
};

// ─── Type compatibility ────────────────────────────────────────────────────────

static bool type_compatible(const std::string& declared, const std::string& actual) {
    if (declared == kUnknown || actual == kUnknown) return true;
    if (declared == actual) return true;

    // Nullable: T? accepts null or any value compatible with T
    if (!declared.empty() && declared.back() == '?') {
        if (actual == kNull) return true;
        return type_compatible(declared.substr(0, declared.size() - 1), actual);
    }

    if (declared == kNumber && (actual == kInt || actual == kFloat)) return true;
    if (kFixedInts.count(actual)  && (declared == kInt   || declared == kNumber)) return true;
    if (kFixedFloats.count(actual) && (declared == kFloat || declared == kNumber)) return true;

    // Widening for fixed-size signed ints
    static const std::unordered_map<std::string, int> kIntW  = {
        {"int8",8},{"int16",16},{"int32",32},{"int64",64}
    };
    static const std::unordered_map<std::string, int> kUIntW = {
        {"uint8",8},{"uint16",16},{"uint32",32},{"uint64",64}
    };
    {
        auto ia = kIntW.find(actual), id = kIntW.find(declared);
        if (ia != kIntW.end() && id != kIntW.end())
            return ia->second <= id->second;
        auto ua = kUIntW.find(actual), ud = kUIntW.find(declared);
        if (ua != kUIntW.end() && ud != kUIntW.end())
            return ua->second <= ud->second;
    }
    if (actual == "float32" && declared == "float64") return true;

    // Generic types: list[T] or dict[K, V]
    auto d_br = declared.find('[');
    if (d_br != std::string::npos) {
        std::string d_base = declared.substr(0, d_br);
        if (actual == d_base) return true; // bare list/dict satisfies generic

        auto a_br = actual.find('[');
        if (a_br != std::string::npos) {
            std::string a_base = actual.substr(0, a_br);
            if (d_base != a_base) return false;

            std::string d_inner = declared.substr(d_br + 1, declared.size() - d_br - 2);
            std::string a_inner = actual.substr(a_br + 1, actual.size() - a_br - 2);

            if (d_base == kList) return type_compatible(d_inner, a_inner);

            if (d_base == kDict) {
                // Split 'K, V' at first depth-0 comma
                auto split_kv = [](const std::string& s) -> std::pair<std::string,std::string> {
                    int depth = 0;
                    for (size_t i = 0; i < s.size(); ++i) {
                        if (s[i] == '[') ++depth;
                        else if (s[i] == ']') --depth;
                        else if (s[i] == ',' && depth == 0) {
                            std::string k = s.substr(0, i);
                            std::string v = s.substr(i + 1);
                            while (!k.empty() && k.back() == ' ') k.pop_back();
                            while (!v.empty() && v.front() == ' ') v.erase(v.begin());
                            return {k, v};
                        }
                    }
                    return {s, ""};
                };
                auto d_kv = split_kv(d_inner);
                auto a_kv = split_kv(a_inner);
                return type_compatible(d_kv.first, a_kv.first) &&
                       type_compatible(d_kv.second, a_kv.second);
            }
        }
    }

    return false;
}

// ─── Binding ───────────────────────────────────────────────────────────────────

struct Binding {
    std::string type;
    int         line      = 0;
    int         col       = 0;
    bool        tracked   = false;
    bool        is_import = false;
    bool        is_param  = false;
    bool        used      = false;
};

// ─── TypeEnv ───────────────────────────────────────────────────────────────────

struct TypeEnv {
    explicit TypeEnv(TypeEnv* p = nullptr) : parent(p) {}

    std::unordered_map<std::string, Binding> bindings;
    std::unordered_set<std::string>          constants;
    TypeEnv*                                 parent = nullptr; // non-owning

    void define(const std::string& name, const std::string& type,
                int line = 0, int col = 0,
                bool is_import = false, bool is_param = false) {
        bool track = (line > 0) && !name.empty() && name[0] != '_';
        bindings[name] = {type, line, col, track, is_import, is_param, false};
    }

    void define_const(const std::string& name, const std::string& type,
                      int line = 0, int col = 0) {
        bool track = (line > 0) && !name.empty() && name[0] != '_';
        bindings[name] = {type, line, col, track, false, false, false};
        constants.insert(name);
    }

    bool is_const(const std::string& name) const {
        if (constants.count(name)) return true;
        return parent && parent->is_const(name);
    }

    bool is_defined(const std::string& name) const {
        if (bindings.count(name)) return true;
        return parent && parent->is_defined(name);
    }

    void update(const std::string& name, const std::string& type) {
        auto it = bindings.find(name);
        if (it != bindings.end()) {
            it->second.type = type;
        } else if (parent) {
            parent->update(name, type);
        } else {
            bindings[name] = {type, 0, 0, false, false, false, false};
        }
    }

    std::string lookup(const std::string& name) const {
        auto it = bindings.find(name);
        if (it != bindings.end()) return it->second.type;
        return parent ? parent->lookup(name) : kUnknown;
    }

    void mark_used(const std::string& name) {
        auto it = bindings.find(name);
        if (it != bindings.end()) {
            it->second.used = true;
        } else if (parent) {
            parent->mark_used(name);
        }
    }

    void collect_all_names(std::unordered_set<std::string>& out) const {
        for (auto& kv : bindings) out.insert(kv.first);
        if (parent) parent->collect_all_names(out);
    }
};

// ─── Function signature ────────────────────────────────────────────────────────

struct FuncSignature {
    std::vector<std::string> param_names;
    std::vector<std::string> param_types;
    std::string              return_type = kUnknown;
    bool                     is_variadic = false;
    int                      min_arity   = -1;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

static std::unordered_set<std::string> set_diff(
    const std::unordered_set<std::string>& a,
    const std::unordered_set<std::string>& b)
{
    std::unordered_set<std::string> result;
    for (auto& s : a) {
        if (!b.count(s)) result.insert(s);
    }
    return result;
}

static std::unordered_set<std::string> set_intersect(
    const std::unordered_set<std::string>& a,
    const std::unordered_set<std::string>& b)
{
    std::unordered_set<std::string> result;
    for (auto& s : a) {
        if (b.count(s)) result.insert(s);
    }
    return result;
}

// ─── TypeChecker ───────────────────────────────────────────────────────────────

class TypeChecker {
public:
    std::vector<TypeCheckError>                     errors;
    TypeEnv                                         global_env;
    TypeEnv*                                        env            = &global_env;
    std::unordered_map<std::string, FuncSignature>  functions;
    std::string                                     current_return = kUnknown;
    int                                             fn_depth       = 0;
    std::unordered_set<std::string>                 definite;
    std::vector<std::unordered_set<std::string>>    definite_stack;
    std::unordered_map<std::string,
        std::unordered_map<std::string,std::string>> class_attrs;
    bool        collecting_for_active = false;
    std::string collecting_for;

    TypeChecker() { setup_builtins(); }

    // ── Error helper ──────────────────────────────────────────────────────────

    void emit(const std::string& msg, int line = 0, int col = 0,
              const std::string& kind = "TypeCheckFault") {
        errors.push_back({msg, line, col, kind});
    }

    // ── Unused reporting ──────────────────────────────────────────────────────

    void report_unused(TypeEnv* e, bool check_locals, bool check_imports) {
        for (auto& kv : e->bindings) {
            const auto& name = kv.first;
            const auto& b    = kv.second;
            if (!b.tracked || b.used) continue;
            if (b.is_import && check_imports) {
                emit("Import '" + name + "' imported but never used",
                     b.line, b.col, "UnusedImportFault");
            } else if (!b.is_import && check_locals) {
                std::string kind = b.is_param ? "Parameter" : "Variable";
                emit(kind + " '" + name + "' declared but never used",
                     b.line, b.col, "UnusedVariableFault");
            }
        }
    }

    // ── Scope helpers ─────────────────────────────────────────────────────────

    void push_definite() {
        definite_stack.push_back(definite);
    }

    void pop_definite() {
        definite = definite_stack.back();
        definite_stack.pop_back();
    }

    // Initialize definite set for a new function scope.
    void init_definite_for_function(const std::vector<std::string>& param_names) {
        std::unordered_set<std::string> all;
        env->collect_all_names(all);
        definite = all;
        for (auto& p : param_names) definite.insert(p);
    }

    // ── Expression visitor ────────────────────────────────────────────────────

    std::string visit_expr(const Expr* e) {
        if (!e) return kNull;
        switch (e->kind) {
            case NodeKind::IntLit:      return kInt;
            case NodeKind::FloatLit:    return kFloat;
            case NodeKind::StringLit:   return kString;
            case NodeKind::BoolLit:     return kBool;
            case NodeKind::NullLit:     return kNull;
            case NodeKind::Identifier:
                return visit_identifier(static_cast<const Identifier*>(e));
            case NodeKind::UnaryOp:
                return visit_unary(static_cast<const UnaryOp*>(e));
            case NodeKind::BinaryOp:
                return visit_binary(static_cast<const BinaryOp*>(e));
            case NodeKind::Call:
                return visit_call(static_cast<const Call*>(e));
            case NodeKind::ListLit:
                return visit_list(static_cast<const ListLit*>(e));
            case NodeKind::DictLit:
                return visit_dict(static_cast<const DictLit*>(e));
            case NodeKind::IndexAccess:
                return visit_index_access(static_cast<const IndexAccess*>(e));
            case NodeKind::Attribute:
                return visit_attribute(static_cast<const Attribute*>(e));
            case NodeKind::FStringLit:
                return visit_fstring(static_cast<const FStringLit*>(e));
            case NodeKind::Match:
                return visit_match(static_cast<const Match*>(e));
            case NodeKind::Lambda:
                return visit_lambda(static_cast<const Lambda*>(e));
            default:
                return kUnknown;
        }
    }

    // ── Statement visitor ─────────────────────────────────────────────────────

    void visit_stmt(const Stmt* s) {
        if (!s) return;
        switch (s->kind) {
            case NodeKind::ExprStmt:
                visit_expr(static_cast<const ExprStmt*>(s)->expr.get());
                break;
            case NodeKind::Assign:
                visit_assign(static_cast<const Assign*>(s));
                break;
            case NodeKind::CompoundAssign:
                visit_compound_assign(static_cast<const Assign*>(s));
                break;
            case NodeKind::TypedAssign:
                visit_typed_assign(static_cast<const TypedAssign*>(s));
                break;
            case NodeKind::ConstDecl:
                visit_const_decl(static_cast<const ConstDecl*>(s));
                break;
            case NodeKind::If:
                visit_if(static_cast<const If*>(s));
                break;
            case NodeKind::While:
                visit_while(static_cast<const While*>(s));
                break;
            case NodeKind::For:
                visit_for(static_cast<const For*>(s));
                break;
            case NodeKind::ForEach:
                visit_foreach(static_cast<const ForEach*>(s));
                break;
            case NodeKind::Return:
                visit_return(static_cast<const Return*>(s));
                break;
            case NodeKind::FuncDef:
                visit_funcdef(static_cast<const FuncDef*>(s));
                break;
            case NodeKind::StructDef:
                visit_structdef(static_cast<const StructDef*>(s));
                break;
            case NodeKind::ClassDef:
                visit_classdef(static_cast<const ClassDef*>(s));
                break;
            case NodeKind::AttrAssign:
                visit_attr_assign(static_cast<const AttrAssign*>(s));
                break;
            case NodeKind::IndexAssign:
                visit_index_assign(static_cast<const IndexAssign*>(s));
                break;
            case NodeKind::Import:
                visit_import(static_cast<const Import*>(s));
                break;
            case NodeKind::Attempt:
                visit_attempt(static_cast<const Attempt*>(s));
                break;
            case NodeKind::Alert:
                visit_alert(static_cast<const Alert*>(s));
                break;
            case NodeKind::Switch:
                visit_switch(static_cast<const Switch*>(s));
                break;
            case NodeKind::Break:
            case NodeKind::Continue:
            case NodeKind::Pass:
                break;
            default:
                break;
        }
    }

    // ── Identifier ────────────────────────────────────────────────────────────

    std::string visit_identifier(const Identifier* n) {
        env->mark_used(n->name);
        if (fn_depth > 0 && !definite.count(n->name) && n->name != "super") {
            emit("Variable '" + n->name + "' may be used before being assigned",
                 n->pos.line, n->pos.col, "UninitializedFault");
        }
        return env->lookup(n->name);
    }

    // ── Assign ───────────────────────────────────────────────────────────────

    void visit_assign(const Assign* n) {
        if (env->is_const(n->name)) {
            emit("Cannot reassign constant '" + n->name + "'",
                 n->pos.line, n->pos.col);
        }
        auto typ = visit_expr(n->value.get());
        if (fn_depth > 0 && !env->is_defined(n->name)) {
            env->define(n->name, typ, n->pos.line, n->pos.col);
        } else {
            env->update(n->name, typ);
        }
        definite.insert(n->name);
    }

    void visit_compound_assign(const Assign* n) {
        // LHS is both read and written; just visit the RHS and mark used.
        env->mark_used(n->name);
        visit_expr(n->value.get());
    }

    // ── TypedAssign ──────────────────────────────────────────────────────────

    void visit_typed_assign(const TypedAssign* n) {
        auto actual = visit_expr(n->value.get());
        if (!type_compatible(n->type_name, actual)) {
            emit("Variable '" + n->name + "' declared as '" + n->type_name +
                 "' but assigned a '" + actual + "' value",
                 n->pos.line, n->pos.col);
        }
        if (fn_depth > 0) {
            env->define(n->name, n->type_name, n->pos.line, n->pos.col);
        } else {
            env->update(n->name, n->type_name);
        }
        definite.insert(n->name);
    }

    // ── ConstDecl ────────────────────────────────────────────────────────────

    void visit_const_decl(const ConstDecl* n) {
        auto actual   = visit_expr(n->value.get());
        auto declared = n->type_name.empty() ? actual : n->type_name;
        if (!n->type_name.empty() && !type_compatible(n->type_name, actual)) {
            emit("Constant '" + n->name + "' declared as '" + n->type_name +
                 "' but assigned a '" + actual + "' value",
                 n->pos.line, n->pos.col);
        }
        int track_line = (fn_depth > 0) ? n->pos.line : 0;
        env->define_const(n->name, declared, track_line, n->pos.col);
        definite.insert(n->name);
    }

    // ── Unary ────────────────────────────────────────────────────────────────

    std::string visit_unary(const UnaryOp* n) {
        auto typ = visit_expr(n->operand.get());
        if (n->op == UnOp::Not) return kBool;
        if (n->op == UnOp::Neg && typ != kUnknown && !kNumeric.count(typ)) {
            emit("Unary '-' requires a number, got '" + typ + "'",
                 n->pos.line, n->pos.col);
        }
        return typ;
    }

    // ── Binary ───────────────────────────────────────────────────────────────

    std::string visit_binary(const BinaryOp* n) {
        auto left  = visit_expr(n->lhs.get());
        auto right = visit_expr(n->rhs.get());
        auto op    = n->op;

        // Comparison / logical ops always produce bool
        switch (op) {
            case BinOp::Eq: case BinOp::Ne:
            case BinOp::Lt: case BinOp::Le:
            case BinOp::Gt: case BinOp::Ge:
            case BinOp::And: case BinOp::Or:
                return kBool;
            default: break;
        }

        if (left != kUnknown && right != kUnknown) {
            bool is_str_rep = (op == BinOp::Mul &&
                ((left == kString && kNumeric.count(right)) ||
                 (right == kString && kNumeric.count(left))));

            if (!is_str_rep) {
                switch (op) {
                    case BinOp::Sub: case BinOp::Div: case BinOp::FloorDiv:
                    case BinOp::Mod: case BinOp::Pow: case BinOp::Mul:
                        if (!kNumeric.count(left)) {
                            emit("Operator requires a number but left operand is '" + left + "'",
                                 n->pos.line, n->pos.col);
                        }
                        if (!kNumeric.count(right)) {
                            emit("Operator requires a number but right operand is '" + right + "'",
                                 n->pos.line, n->pos.col);
                        }
                        break;
                    case BinOp::Add: {
                        static const std::unordered_set<std::string> addable =
                            {kInt, kFloat, kNumber, kString, kList};
                        if (addable.count(left) && addable.count(right)) {
                            bool both_num = kNumeric.count(left) && kNumeric.count(right);
                            if (left != right && !both_num) {
                                emit("Operator '+' cannot combine '" + left +
                                     "' and '" + right + "'",
                                     n->pos.line, n->pos.col);
                            }
                        }
                        break;
                    }
                    default: break;
                }
            }
        }

        return binop_result(op, left, right);
    }

    std::string binop_result(BinOp op, const std::string& left, const std::string& right) {
        if (op == BinOp::Div) return kFloat;
        if (op == BinOp::FloorDiv) return kInt;

        switch (op) {
            case BinOp::Add: case BinOp::Sub: case BinOp::Mul:
            case BinOp::Mod: case BinOp::Pow: {
                if (kNumeric.count(left) && kNumeric.count(right)) {
                    bool any_float = (left == kFloat || right == kFloat ||
                                      kFixedFloats.count(left) || kFixedFloats.count(right));
                    return any_float ? kFloat : kInt;
                }
                if (op == BinOp::Add && left == right &&
                    (left == kString || left == kList))
                    return left;
                if (op == BinOp::Mul) {
                    if (left == kString && kNumeric.count(right)) return kString;
                    if (right == kString && kNumeric.count(left)) return kString;
                }
                break;
            }
            default: break;
        }
        return kUnknown;
    }

    // ── Call ─────────────────────────────────────────────────────────────────

    std::string visit_call(const Call* n) {
        std::string callee_name;
        if (n->callee->kind == NodeKind::Identifier) {
            callee_name = static_cast<const Identifier*>(n->callee.get())->name;
            env->mark_used(callee_name);
        } else {
            visit_expr(n->callee.get());
        }

        std::vector<std::string> arg_types;
        arg_types.reserve(n->args.size());
        for (auto& a : n->args) arg_types.push_back(visit_expr(a.get()));

        if (!callee_name.empty()) {
            auto it = functions.find(callee_name);
            if (it != functions.end()) {
                auto& sig = it->second;
                if (!sig.is_variadic) {
                    int min_a  = sig.min_arity >= 0 ? sig.min_arity : (int)sig.param_types.size();
                    int max_a  = (int)sig.param_types.size();
                    int n_args = (int)arg_types.size();
                    if (n_args < min_a || n_args > max_a) {
                        if (min_a == max_a) {
                            emit("'" + callee_name + "' expects " + std::to_string(max_a) +
                                 " argument(s), got " + std::to_string(n_args),
                                 n->pos.line, n->pos.col);
                        } else {
                            emit("'" + callee_name + "' expects " +
                                 std::to_string(min_a) + "–" + std::to_string(max_a) +
                                 " argument(s), got " + std::to_string(n_args),
                                 n->pos.line, n->pos.col);
                        }
                    } else {
                        for (size_t i = 0; i < arg_types.size() && i < sig.param_types.size(); ++i) {
                            if (!type_compatible(sig.param_types[i], arg_types[i])) {
                                emit("Argument '" + sig.param_names[i] + "' of '" + callee_name +
                                     "' expects '" + sig.param_types[i] +
                                     "', got '" + arg_types[i] + "'",
                                     n->pos.line, n->pos.col);
                            }
                        }
                    }
                }
                return sig.return_type;
            }
        }
        return kUnknown;
    }

    // ── ListLit ───────────────────────────────────────────────────────────────

    std::string visit_list(const ListLit* n) {
        if (n->elements.empty()) return kList;

        std::vector<std::string> elem_types;
        elem_types.reserve(n->elements.size());
        for (auto& e : n->elements) elem_types.push_back(visit_expr(e.get()));

        auto& first = elem_types[0];
        bool uniform = first != kUnknown &&
            std::all_of(elem_types.begin(), elem_types.end(),
                [&first](const std::string& t) { return t == first; });
        return uniform ? (kList + "[" + first + "]") : kList;
    }

    // ── DictLit ───────────────────────────────────────────────────────────────

    std::string visit_dict(const DictLit* n) {
        if (n->pairs.empty()) return kDict;

        std::vector<std::string> key_types, val_types;
        for (auto& p : n->pairs) {
            key_types.push_back(visit_expr(p.key.get()));
            val_types.push_back(visit_expr(p.value.get()));
        }

        auto& k0 = key_types[0];
        auto& v0 = val_types[0];
        bool k_uni = k0 != kUnknown && std::all_of(key_types.begin(), key_types.end(),
                         [&k0](const std::string& t){ return t == k0; });
        bool v_uni = v0 != kUnknown && std::all_of(val_types.begin(), val_types.end(),
                         [&v0](const std::string& t){ return t == v0; });
        if (k_uni && v_uni) return kDict + "[" + k0 + ", " + v0 + "]";
        return kDict;
    }

    // ── IndexAccess ──────────────────────────────────────────────────────────

    std::string visit_index_access(const IndexAccess* n) {
        visit_expr(n->base.get());
        visit_expr(n->index.get());
        return kUnknown;
    }

    // ── Attribute ────────────────────────────────────────────────────────────

    std::string visit_attribute(const Attribute* n) {
        auto obj_type = visit_expr(n->object.get());
        auto it = class_attrs.find(obj_type);
        if (it != class_attrs.end()) {
            auto attr_it = it->second.find(n->name);
            if (attr_it != it->second.end()) return attr_it->second;
        }
        return kUnknown;
    }

    // ── FStringLit ────────────────────────────────────────────────────────────

    std::string visit_fstring(const FStringLit* n) {
        for (auto& part : n->parts) {
            if (part.kind == FStringPart::Kind::Expr) visit_expr(part.expr.get());
        }
        return kString;
    }

    // ── Match ────────────────────────────────────────────────────────────────

    std::string visit_match(const Match* n) {
        visit_expr(n->subject.get());
        for (auto& arm : n->arms) {
            for (auto& p : arm.patterns) visit_expr(p.get());
            visit_expr(arm.result.get());
        }
        return kUnknown;
    }

    // ── Lambda ───────────────────────────────────────────────────────────────

    std::string visit_lambda(const Lambda* n) {
        std::vector<std::string> pnames;
        auto child = std::make_unique<TypeEnv>(env);
        for (auto& p : n->params) {
            pnames.push_back(p.name);
            auto pt = p.type_name.empty() ? kUnknown : p.type_name;
            child->define(p.name, pt, 0, 0, false, true);
            if (p.default_val) visit_expr(p.default_val.get());
        }

        push_definite();
        init_definite_for_function(pnames);

        auto* saved = env;
        env = child.get();
        ++fn_depth;

        if (n->expr_body) {
            visit_expr(n->expr_body.get());
        } else {
            for (auto& s : n->block_body) visit_stmt(s.get());
        }

        --fn_depth;
        report_unused(child.get(), true, true);
        env = saved;
        pop_definite();
        return kFunction;
    }

    // ── Return ───────────────────────────────────────────────────────────────

    void visit_return(const Return* n) {
        auto actual = n->value ? visit_expr(n->value.get()) : kNull;
        if (!type_compatible(current_return, actual)) {
            emit("Function declared to return '" + current_return +
                 "' but returns '" + actual + "'",
                 n->pos.line, n->pos.col);
        }
    }

    // ── FuncDef ──────────────────────────────────────────────────────────────

    void visit_funcdef(const FuncDef* n) {
        std::vector<std::string> pnames, ptypes;
        int  min_arity  = 0;
        bool is_variadic = false;

        for (auto& p : n->params) {
            pnames.push_back(p.name);
            auto pt = p.type_name.empty() ? kUnknown : p.type_name;
            ptypes.push_back(p.variadic ? kList : pt);
            if (!p.default_val && !p.variadic) ++min_arity;
            if (p.variadic) is_variadic = true;
        }

        auto ret = n->return_type.empty() ? kUnknown : n->return_type;
        FuncSignature sig{pnames, ptypes, ret, is_variadic, min_arity};

        if (!n->name.empty()) {
            functions[n->name] = sig;
            env->define(n->name, kFunction);
        }

        auto child = std::make_unique<TypeEnv>(env);
        for (size_t i = 0; i < n->params.size(); ++i) {
            auto& p = n->params[i];
            child->define(p.name, ptypes[i], n->pos.line, 0, false, true);
            if (p.default_val) visit_expr(p.default_val.get());
        }

        push_definite();
        init_definite_for_function(pnames);

        auto* saved_env = env;
        auto  saved_ret = current_return;
        env            = child.get();
        current_return = ret;
        ++fn_depth;

        for (auto& s : n->body) visit_stmt(s.get());

        --fn_depth;
        report_unused(child.get(), true, true);
        env            = saved_env;
        current_return = saved_ret;
        pop_definite();
    }

    // ── StructDef ────────────────────────────────────────────────────────────

    void visit_structdef(const StructDef* n) {
        env->define(n->name, kUnknown);
        for (auto& f : n->fields) {
            if (f.default_val) visit_expr(f.default_val.get());
        }
    }

    // ── ClassDef ─────────────────────────────────────────────────────────────

    void visit_classdef(const ClassDef* n) {
        env->define(n->name, kUnknown);
        functions[n->name] = FuncSignature{{}, {}, n->name, true, 0};
        class_attrs[n->name] = {};

        for (auto& method : n->methods) {
            if (method->kind != NodeKind::FuncDef) continue;
            auto* mdef   = static_cast<const FuncDef*>(method.get());
            bool is_init = (mdef->name == "init");
            if (is_init) { collecting_for = n->name; collecting_for_active = true; }
            visit_funcdef(mdef);
            if (is_init) { collecting_for_active = false; }
        }
    }

    // ── AttrAssign ──────────────────────────────────────────────────────────

    void visit_attr_assign(const AttrAssign* n) {
        visit_expr(n->object.get());
        auto val_type = visit_expr(n->value.get());

        if (collecting_for_active &&
            n->object->kind == NodeKind::Identifier &&
            static_cast<const Identifier*>(n->object.get())->name == "self") {
            auto& attrs = class_attrs[collecting_for];
            if (!attrs.count(n->attr)) attrs[n->attr] = val_type;
        }
    }

    // ── IndexAssign ─────────────────────────────────────────────────────────

    void visit_index_assign(const IndexAssign* n) {
        visit_expr(n->base.get());
        visit_expr(n->index.get());
        visit_expr(n->value.get());
    }

    // ── If ───────────────────────────────────────────────────────────────────

    void visit_if(const If* n) {
        bool in_fn = fn_depth > 0;
        auto def_before = definite;
        std::vector<std::unordered_set<std::string>> branch_adds;

        for (auto& branch : n->branches) {
            visit_expr(branch.condition.get());
            auto child = std::make_unique<TypeEnv>(env);
            auto* saved = env;
            env = child.get();
            definite = def_before;
            for (auto& s : branch.body) visit_stmt(s.get());
            branch_adds.push_back(set_diff(definite, def_before));
            report_unused(child.get(), in_fn, true);
            env = saved;
        }

        bool has_else = !n->else_body.empty();
        if (has_else) {
            auto child = std::make_unique<TypeEnv>(env);
            auto* saved = env;
            env = child.get();
            definite = def_before;
            for (auto& s : n->else_body) visit_stmt(s.get());
            branch_adds.push_back(set_diff(definite, def_before));
            report_unused(child.get(), in_fn, true);
            env = saved;
        }

        definite = def_before;
        if (has_else && !branch_adds.empty()) {
            auto guaranteed = branch_adds[0];
            for (size_t i = 1; i < branch_adds.size(); ++i) {
                guaranteed = set_intersect(guaranteed, branch_adds[i]);
            }
            for (auto& s : guaranteed) definite.insert(s);
        }
    }

    // ── While ────────────────────────────────────────────────────────────────

    void visit_while(const While* n) {
        visit_expr(n->condition.get());
        auto saved = definite;
        for (auto& s : n->body) visit_stmt(s.get());
        definite = saved;
    }

    // ── For ─────────────────────────────────────────────────────────────────

    void visit_for(const For* n) {
        visit_expr(n->start.get());
        visit_expr(n->end.get());
        if (n->step) visit_expr(n->step.get());

        bool in_fn = fn_depth > 0;
        auto child  = std::make_unique<TypeEnv>(env);
        child->define(n->var, kInt, in_fn ? n->pos.line : 0, n->pos.col);

        auto* saved = env;
        env = child.get();
        auto saved_def = definite;
        definite.insert(n->var);
        for (auto& s : n->body) visit_stmt(s.get());
        definite = saved_def;
        report_unused(child.get(), in_fn, true);
        env = saved;
    }

    // ── ForEach ──────────────────────────────────────────────────────────────

    void visit_foreach(const ForEach* n) {
        visit_expr(n->iterable.get());

        bool in_fn = fn_depth > 0;
        auto child  = std::make_unique<TypeEnv>(env);
        child->define(n->var, kUnknown, in_fn ? n->pos.line : 0, n->pos.col);

        auto* saved = env;
        env = child.get();
        auto saved_def = definite;
        definite.insert(n->var);
        for (auto& s : n->body) visit_stmt(s.get());
        definite = saved_def;
        report_unused(child.get(), in_fn, true);
        env = saved;
    }

    // ── Import ───────────────────────────────────────────────────────────────

    void visit_import(const Import* n) {
        if (!n->alias.empty()) {
            env->define(n->alias, kUnknown, n->pos.line, n->pos.col, true);
        } else {
            for (auto& name : n->names) {
                env->define(name, kUnknown, n->pos.line, n->pos.col, true);
            }
        }
    }

    // ── Attempt ──────────────────────────────────────────────────────────────

    void visit_attempt(const Attempt* n) {
        bool in_fn = fn_depth > 0;
        for (auto& s : n->try_body) visit_stmt(s.get());

        auto rescue_env = std::make_unique<TypeEnv>(env);
        if (!n->error_var.empty()) {
            rescue_env->define(n->error_var, kString,
                               in_fn ? n->pos.line : 0, n->pos.col);
        }
        auto* saved = env;
        env = rescue_env.get();
        for (auto& s : n->catch_body) visit_stmt(s.get());
        report_unused(rescue_env.get(), in_fn, true);
        env = saved;

        for (auto& s : n->finally_body) visit_stmt(s.get());
    }

    // ── Alert ────────────────────────────────────────────────────────────────

    void visit_alert(const Alert* n) { visit_expr(n->expr.get()); }

    // ── Switch ───────────────────────────────────────────────────────────────

    void visit_switch(const Switch* n) {
        visit_expr(n->subject.get());
        for (auto& c : n->cases) {
            for (auto& v : c.values) visit_expr(v.get());
            for (auto& s : c.body)   visit_stmt(s.get());
        }
        for (auto& s : n->else_body) visit_stmt(s.get());
    }

    // ── Built-in signatures ───────────────────────────────────────────────────

    void setup_builtins() {
        auto def = [&](std::string name,
                       std::vector<std::string> pnames,
                       std::vector<std::string> ptypes,
                       std::string ret,
                       bool variadic = false,
                       int  min_a    = -1) {
            int arity = (min_a >= 0) ? min_a : (variadic ? 0 : (int)pnames.size());
            functions[name] = FuncSignature{
                std::move(pnames), std::move(ptypes), std::move(ret), variadic, arity
            };
            env->define(name, kFunction);
        };

        def("write",    {"value"},              {kUnknown},                      kNull,   true);
        def("len",      {"x"},                  {kUnknown},                      kInt);
        def("to_int",   {"x"},                  {kUnknown},                      kInt);
        def("to_float", {"x"},                  {kUnknown},                      kFloat);
        def("to_str",   {"x"},                  {kUnknown},                      kString);
        def("to_bool",  {"x"},                  {kUnknown},                      kBool);
        def("typeof",   {"x"},                  {kUnknown},                      kString);
        def("sqrt",     {"x"},                  {kNumber},                       kFloat);
        def("abs",      {"x"},                  {kNumber},                       kNumber);
        def("round",    {"x"},                  {kNumber},                       kNumber);
        def("floor",    {"x"},                  {kNumber},                       kInt);
        def("ceil",     {"x"},                  {kNumber},                       kInt);
        def("exp",      {"x"},                  {kNumber},                       kFloat);
        def("ln",       {"x"},                  {kNumber},                       kFloat);
        def("append",   {"lst","val"},           {kList, kUnknown},               kNull);
        def("pop",      {"lst"},                 {kList},                         kUnknown, true);
        def("insert",   {"lst","idx","val"},     {kList, kInt, kUnknown},         kNull);
        def("keys",     {"d"},                   {kDict},                         kList);
        def("values",   {"d"},                   {kDict},                         kList);
        def("split",    {"s"},                   {kString},                       kList,   true);
        def("join",     {"sep","lst"},           {kString, kList},                kString);
        def("range",    {"start","end"},         {kInt, kInt},                    kList,   true);
        def("min",      {"x"},                   {kUnknown},                      kUnknown, true);
        def("max",      {"x"},                   {kUnknown},                      kUnknown, true);
        def("sum",      {"lst"},                 {kList},                         kNumber);
        def("clamp",    {"x","low","high"},      {kNumber, kNumber, kNumber},     kNumber);
        def("alert",    {"msg"},                 {kUnknown},                      kNull);
    }

    // ── Entry point ───────────────────────────────────────────────────────────

    std::vector<TypeCheckError> check(const Program& prog) {
        for (auto& s : prog.statements) visit_stmt(s.get());
        report_unused(env, /*check_locals=*/false, /*check_imports=*/true);
        return errors;
    }
};

// ─── Public API ───────────────────────────────────────────────────────────────

std::vector<TypeCheckError> type_check(const Program& program) {
    return TypeChecker{}.check(program);
}

}  // namespace luz
