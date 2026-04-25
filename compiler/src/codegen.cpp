// codegen.cpp — LLVM IR text emitter.
//
// Two-pass strategy:
//   Pass 1: walk the HIR and intern all string literals → global constants.
//   Pass 2: emit the module header, string pool, then all function/stmt bodies.
//
// Variables use alloca/store/load so we never need to build SSA phi nodes.
// Each function gets a fresh temporary counter so names stay short (%t0, %t1 …).

#include "luz/codegen.hpp"

#include <cassert>
#include <cstdio>
#include <ostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace luz {
namespace {

// ── Helpers ───────────────────────────────────────────────────────────────────

std::string llvm_type(const std::string& hir_type) {
    if (hir_type == "int"   || hir_type == "int?"   ) return "i64";
    if (hir_type == "float" || hir_type == "float?" ) return "double";
    if (hir_type == "bool"  || hir_type == "bool?"  ) return "i1";
    if (hir_type == "string"|| hir_type == "string?") return "i8*";
    if (hir_type == "dict"  || hir_type == "list"   ) return "i8*";
    if (hir_type == "void"  || hir_type.empty()     ) return "void";
    return "i64";  // user-defined / unknown → treat as opaque i64
}

std::string escape_ir_string(const std::string& s) {
    std::string out;
    for (unsigned char c : s) {
        if      (c == '"' ) out += "\\22";
        else if (c == '\\') out += "\\5C";
        else if (c == '\n') out += "\\0A";
        else if (c == '\r') out += "\\0D";
        else if (c == '\t') out += "\\09";
        else if (c < 32 || c > 126) {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "\\%02X", c);
            out += buf;
        } else {
            out += static_cast<char>(c);
        }
    }
    return out;
}

// ── Val: an LLVM SSA value ────────────────────────────────────────────────────

struct Val {
    std::string name;  // e.g. "%t3", "42", "0.5"
    std::string type;  // e.g. "i64", "double", "i1", "i8*", "void"
};

// ── CodeGen ───────────────────────────────────────────────────────────────────

class CodeGen {
public:
    explicit CodeGen(std::ostream& output) : final_out_(output) {}

    void emit_module(const HirBlock& program, const std::string& filename) {
        collect_strings(program);
        collect_classes(program);

        // Preamble → final output
        final_out_ << "; ModuleID = 'luz'\n"
                   << "source_filename = \"" << filename << "\"\n\n";

        final_out_ << "declare i32 @printf(i8* nocapture readonly, ...)\n"
                   << "declare void @exit(i32)\n\n";

        emit_string_pool();
        emit_format_strings();

        // Separate top-level nodes by kind
        std::vector<HirNode*> classes, funcs, stmts;
        for (auto& n : program) {
            if      (n->kind == HirKind::ClassDef) classes.push_back(n.get());
            else if (n->kind == HirKind::FuncDef)  funcs.push_back(n.get());
            else                                   stmts.push_back(n.get());
        }

        // Emit class methods before free functions
        for (auto* c : classes)
            emit_class(static_cast<HirClassDef*>(c));

        // Emit free functions
        for (auto* f : funcs)
            emit_func(static_cast<HirFuncDef*>(f));

        // Emit powi helper if ** operator was used
        if (needs_powi_) emit_powi_helper();

        // Emit main()
        reset_counters();
        out_ = &body_buf_;
        current_ret_type_ = "i32";

        final_out_ << "\ndefine i32 @main() {\n"
                   << "entry:\n";

        for (auto* s : stmts) emit_stmt(s);

        emit_line("ret i32 0");
        final_out_ << body_buf_.str() << "}\n";
    }

private:
    std::ostream& final_out_;

    // During function / main emission we write to body_buf_; then dump it.
    std::ostringstream body_buf_;
    std::ostream*      out_ = &body_buf_;

    // String literal pool (index → raw content)
    std::vector<std::string>         str_pool_;
    std::unordered_map<std::string, int> str_dedup_;

    // Class registry for method dispatch
    struct ClassInfo {
        std::string parent;
        std::vector<std::string> methods;
        std::unordered_map<std::string, std::string> field_types;        // field  → llvm type
        std::unordered_map<std::string, std::string> method_ret_types;   // method → llvm type
    };
    std::unordered_map<std::string, ClassInfo> classes_;

    // Per-function state (reset on each function)
    int tmp_id_   = 0;
    int label_id_ = 0;
    struct AllocaInfo { std::string ptr; std::string type; std::string hir_type; };
    std::unordered_map<std::string, AllocaInfo> locals_;
    struct LoopInfo { std::string cond_lbl; std::string exit_lbl; };
    std::vector<LoopInfo> loop_stack_;
    std::string current_ret_type_ = "i64";

    bool needs_powi_ = false;

    // ── Counter helpers ───────────────────────────────────────────────────────

    void reset_counters() {
        tmp_id_ = label_id_ = 0;
        locals_.clear();
        loop_stack_.clear();
        body_buf_.str("");
        body_buf_.clear();
        out_ = &body_buf_;
    }

    std::string tmp()                    { return "%t"  + std::to_string(tmp_id_++);   }
    std::string lbl(const std::string& p){ return p     + std::to_string(label_id_++); }

    void emit_line(const std::string& s) { *out_ << "  " << s << "\n"; }

    // ── String pool ───────────────────────────────────────────────────────────

    int intern(const std::string& s) {
        auto res = str_dedup_.emplace(s, (int)str_pool_.size());
        if (res.second) str_pool_.push_back(s);
        return res.first->second;
    }

    void collect_strings(const HirBlock& blk) {
        for (auto& n : blk) collect_node(n.get());
    }

    // Scan init body for self.field = param patterns to record field types.
    void scan_init_fields(const HirBlock& body,
                          const std::unordered_map<std::string, std::string>& param_t,
                          std::unordered_map<std::string, std::string>& field_types) {
        for (auto& node : body) {
            if (node->kind != HirKind::FieldStore) continue;
            auto* fs = static_cast<HirFieldStore*>(node.get());
            if (field_types.count(fs->field)) continue; // already known
            std::string vt;
            if (fs->value->kind == HirKind::Load) {
                auto it = param_t.find(static_cast<HirLoad*>(fs->value.get())->name);
                if (it != param_t.end()) vt = it->second;
            } else if (fs->value->kind == HirKind::Literal) {
                auto* lit = static_cast<HirLiteral*>(fs->value.get());
                switch (lit->vk) {
                case HirLiteral::ValKind::Int:    vt = "i64";    break;
                case HirLiteral::ValKind::Float:  vt = "double"; break;
                case HirLiteral::ValKind::Bool:   vt = "i1";     break;
                case HirLiteral::ValKind::String: vt = "i8*";    break;
                default:                          vt = "i8*";    break;
                }
            }
            if (!vt.empty()) field_types[fs->field] = vt;
        }
    }

    void collect_classes(const HirBlock& program) {
        for (auto& n : program) {
            if (n->kind != HirKind::ClassDef) continue;
            auto* cls = static_cast<HirClassDef*>(n.get());
            ClassInfo info;
            info.parent = cls->parent;
            for (auto& m : cls->methods) {
                if (m->kind != HirKind::FuncDef) continue;
                auto* fn = static_cast<HirFuncDef*>(m.get());
                info.methods.push_back(fn->name);
                // Record return type (unknown → void for methods)
                std::string ret = llvm_type(fn->return_type);
                if (fn->return_type.empty() || fn->return_type == "unknown") ret = "void";
                info.method_ret_types[fn->name] = ret;
                if (fn->name == "init") {
                    std::unordered_map<std::string, std::string> param_t;
                    for (auto& p : fn->params)
                        param_t[p.name] = llvm_type(p.type);
                    scan_init_fields(fn->body, param_t, info.field_types);
                }
            }
            classes_[cls->name] = std::move(info);
        }
    }

    // Resolve field type: check class hierarchy field_types maps.
    std::string resolve_field_type(const std::string& class_name,
                                   const std::string& field) {
        std::string cur = class_name;
        while (!cur.empty()) {
            auto cit = classes_.find(cur);
            if (cit == classes_.end()) break;
            auto fit = cit->second.field_types.find(field);
            if (fit != cit->second.field_types.end()) return fit->second;
            cur = cit->second.parent;
        }
        return "i8*"; // default: treat as string/pointer
    }

    void collect_node(HirNode* n) {
        if (!n) return;
        switch (n->kind) {
        case HirKind::Literal: {
            auto* l = static_cast<HirLiteral*>(n);
            if (l->vk == HirLiteral::ValKind::String) intern(l->s);
            break;
        }
        case HirKind::Let:    collect_node(static_cast<HirLet*>(n)->value.get()); break;
        case HirKind::Assign: collect_node(static_cast<HirAssign*>(n)->value.get()); break;
        case HirKind::Return: {
            auto* r = static_cast<HirReturn*>(n);
            if (r->value) collect_node(r->value.get());
            break;
        }
        case HirKind::BinOp: {
            auto* b = static_cast<HirBinOp*>(n);
            collect_node(b->left.get()); collect_node(b->right.get());
            break;
        }
        case HirKind::UnaryOp:
            collect_node(static_cast<HirUnaryOp*>(n)->operand.get());
            break;
        case HirKind::Call:
            for (auto& a : static_cast<HirCall*>(n)->args) collect_node(a.get());
            break;
        case HirKind::ExprCall:
            for (auto& a : static_cast<HirExprCall*>(n)->args) collect_node(a.get());
            break;
        case HirKind::If: {
            auto* i = static_cast<HirIf*>(n);
            collect_node(i->cond.get());
            collect_strings(i->then_block);
            collect_strings(i->else_block);
            break;
        }
        case HirKind::While: {
            auto* w = static_cast<HirWhile*>(n);
            collect_node(w->cond.get());
            collect_strings(w->body);
            break;
        }
        case HirKind::FuncDef:
            collect_strings(static_cast<HirFuncDef*>(n)->body);
            break;
        case HirKind::ClassDef: {
            auto* cls = static_cast<HirClassDef*>(n);
            for (auto& m : cls->methods) collect_node(m.get());
            break;
        }
        case HirKind::FieldLoad: {
            auto* f = static_cast<HirFieldLoad*>(n);
            intern(f->field);
            collect_node(f->obj.get());
            break;
        }
        case HirKind::FieldStore: {
            auto* f = static_cast<HirFieldStore*>(n);
            intern(f->field);
            collect_node(f->obj.get());
            collect_node(f->value.get());
            break;
        }
        case HirKind::ObjectCall: {
            auto* o = static_cast<HirObjectCall*>(n);
            collect_node(o->obj.get());
            for (auto& a : o->args) collect_node(a.get());
            break;
        }
        case HirKind::Alert:
            collect_node(static_cast<HirAlert*>(n)->value.get());
            break;
        case HirKind::AttemptRescue: {
            auto* a = static_cast<HirAttemptRescue*>(n);
            collect_strings(a->try_block);
            collect_strings(a->rescue_block);
            collect_strings(a->finally_block);
            break;
        }
        default: break;
        }
    }

    void emit_string_pool() {
        for (int i = 0; i < (int)str_pool_.size(); ++i) {
            int len = (int)str_pool_[i].size() + 1;
            final_out_ << "@.str." << i
                       << " = private unnamed_addr constant [" << len << " x i8] c\""
                       << escape_ir_string(str_pool_[i]) << "\\00\", align 1\n";
        }
        if (!str_pool_.empty()) final_out_ << '\n';
    }

    void emit_format_strings() {
        // Sizes include the null terminator.
        final_out_
            << "@.fmt.int   = private unnamed_addr constant [6 x i8]"
               " c\"%lld\\0A\\00\", align 1\n"
            << "@.fmt.float = private unnamed_addr constant [4 x i8]"
               " c\"%g\\0A\\00\", align 1\n"
            << "@.fmt.str   = private unnamed_addr constant [4 x i8]"
               " c\"%s\\0A\\00\", align 1\n"
            << "@.fmt.true  = private unnamed_addr constant [6 x i8]"
               " c\"true\\0A\\00\", align 1\n"
            << "@.fmt.false = private unnamed_addr constant [7 x i8]"
               " c\"false\\0A\\00\", align 1\n\n";
        
        final_out_
            << "declare i8*  @luz_str_concat(i8*, i8*)\n"
            << "declare i8*  @luz_to_str_int(i64)\n"
            << "declare i8*  @luz_to_str_float(double)\n"
            << "declare i8*  @luz_to_str_bool(i1)\n"
            << "declare i64  @luz_str_len(i8*)\n"
            << "declare i1   @luz_str_eq(i8*, i8*)\n"
            << "declare i1   @luz_str_contains(i8*, i8*)\n\n";

        // Dict runtime
        final_out_
            << "declare i8*  @luz_dict_new()\n"
            << "declare void @luz_dict_set_int(i8*, i8*, i64)\n"
            << "declare void @luz_dict_set_float(i8*, i8*, double)\n"
            << "declare void @luz_dict_set_bool(i8*, i8*, i1)\n"
            << "declare void @luz_dict_set_str(i8*, i8*, i8*)\n"
            << "declare i64  @luz_dict_get_int(i8*, i8*)\n"
            << "declare double @luz_dict_get_float(i8*, i8*)\n"
            << "declare i1   @luz_dict_get_bool(i8*, i8*)\n"
            << "declare i8*  @luz_dict_get_str(i8*, i8*)\n"
            << "declare i64  @luz_dict_len(i8*)\n"
            << "declare i1   @luz_dict_contains(i8*, i8*)\n"
            << "declare void @luz_dict_remove(i8*, i8*)\n\n";
    }

    // Emit a GEP to get an i8* into a global string constant.
    std::string gep_str_const(const std::string& global, int len) {
        std::string t = tmp();
        emit_line(t + " = getelementptr inbounds [" + std::to_string(len) + " x i8], ["
                  + std::to_string(len) + " x i8]* " + global + ", i64 0, i64 0");
        return t;
    }

    std::string gep_pool_str(int id) {
        int len = (int)str_pool_[id].size() + 1;
        return gep_str_const("@.str." + std::to_string(id), len);
    }

    // ── Type inference ────────────────────────────────────────────────────────

    std::string infer_llvm_type(HirNode* n) {
        if (!n) return "void";
        switch (n->kind) {
        case HirKind::Literal: {
            auto* l = static_cast<HirLiteral*>(n);
            switch (l->vk) {
            case HirLiteral::ValKind::Int:    return "i64";
            case HirLiteral::ValKind::Float:  return "double";
            case HirLiteral::ValKind::Bool:   return "i1";
            case HirLiteral::ValKind::String: return "i8*";
            case HirLiteral::ValKind::Null:   return "i64";
            }
            break;
        }
        case HirKind::Load: {
            auto* l = static_cast<HirLoad*>(n);
            auto it = locals_.find(l->name);
            if (it != locals_.end()) return it->second.type;
            return llvm_type(l->type);
        }
        case HirKind::BinOp: {
            auto* b = static_cast<HirBinOp*>(n);
            const std::string& op = b->op;
            if (op == "==" || op == "!=" || op == "<"  || op == "<=" ||
                op == ">"  || op == ">=" || op == "and"|| op == "or")
                return "i1";
            return llvm_type(b->type);
        }
        case HirKind::UnaryOp: {
            auto* u = static_cast<HirUnaryOp*>(n);
            return u->op == "not" ? "i1" : llvm_type(u->type);
        }
        case HirKind::Call:
            return llvm_type(static_cast<HirCall*>(n)->return_type);
        default: break;
        }
        return "i64";
    }

    // ── Expression emission ───────────────────────────────────────────────────

    Val emit_expr(HirNode* n) {
        switch (n->kind) {
        case HirKind::Literal:  return emit_literal(static_cast<HirLiteral*>(n));
        case HirKind::Load:     return emit_load_var(static_cast<HirLoad*>(n));
        case HirKind::BinOp:    return emit_binop(static_cast<HirBinOp*>(n));
        case HirKind::UnaryOp:  return emit_unary(static_cast<HirUnaryOp*>(n));
        case HirKind::Call:     return emit_call(static_cast<HirCall*>(n));
        case HirKind::ExprCall: return emit_exprcall(static_cast<HirExprCall*>(n));
        case HirKind::Dict:       return emit_dict(static_cast<HirDict*>(n));
        case HirKind::Index:      return emit_index_expr(static_cast<HirIndex*>(n));
        case HirKind::FieldLoad:  return emit_field_load(static_cast<HirFieldLoad*>(n));
        case HirKind::ObjectCall: return emit_objectcall(static_cast<HirObjectCall*>(n));
        case HirKind::If:
            // If used as expression (e.g. match desugaring) — emit as stmt, return undef
            emit_if_stmt(static_cast<HirIf*>(n));
            return { "undef", "i64" };
        default:
            return { "0", "i64" };
        }
    }

    Val emit_literal(HirLiteral* n) {
        switch (n->vk) {
        case HirLiteral::ValKind::Int:
            return { std::to_string(n->i), "i64" };
        case HirLiteral::ValKind::Float: {
            std::ostringstream ss;
            ss << n->f;
            std::string s = ss.str();
            if (s.find('.') == std::string::npos &&
                s.find('e') == std::string::npos)
                s += ".0";
            return { s, "double" };
        }
        case HirLiteral::ValKind::Bool:
            return { n->b ? "1" : "0", "i1" };
        case HirLiteral::ValKind::String: {
            int id  = intern(n->s);
            return { gep_pool_str(id), "i8*" };
        }
        case HirLiteral::ValKind::Null:
            return { "0", "i64" };
        }
        return { "0", "i64" };
    }

    Val emit_load_var(HirLoad* n) {
        auto it = locals_.find(n->name);
        if (it == locals_.end()) return { "0", "i64" };
        std::string t = tmp();
        emit_line(t + " = load " + it->second.type + ", "
                  + it->second.type + "* " + it->second.ptr);
        return { t, it->second.type };
    }

    Val emit_binop(HirBinOp* n) {
        Val lv = emit_expr(n->left.get());
        Val rv = emit_expr(n->right.get());
        std::string t = tmp();

        bool is_float = (lv.type == "double" || rv.type == "double");

        if (n->op == "+" && (lv.type == "i8*" || rv.type == "i8*")) {
            std::string la = lv.type != "i8*" ? coerce_to_str(lv) : lv.name;
            std::string ra = rv.type != "i8*" ? coerce_to_str(rv) : rv.name;
            emit_line(t + " = call i8* @luz_str_concat(i8* " + la + ", i8* " + ra + ")");
            return { t, "i8*" };
        }

        // String equality / inequality
        if ((n->op == "==" || n->op == "!=") &&
            (lv.type == "i8*" || rv.type == "i8*")) {
            emit_line(t + " = call i1 @luz_str_eq(i8* " + lv.name + ", i8* " + rv.name + ")");
            if (n->op == "!=") {
                std::string t2 = tmp();
                emit_line(t2 + " = xor i1 " + t + ", 1");
                return { t2, "i1" };
            }
            return { t, "i1" };
        }

        // Logical
        if (n->op == "and") {
            emit_line(t + " = and i1 " + lv.name + ", " + rv.name);
            return { t, "i1" };
        }
        if (n->op == "or") {
            emit_line(t + " = or i1 " + lv.name + ", " + rv.name);
            return { t, "i1" };
        }

        // Comparisons
        static const std::string cmp_ops[] = { "==","!=","<","<=",">",">=" };
        bool is_cmp = false;
        for (auto& s : cmp_ops) if (n->op == s) { is_cmp = true; break; }

        if (is_cmp) {
            std::string instr;
            if (is_float) {
                const char* pred =
                    n->op == "==" ? "oeq" : n->op == "!=" ? "one" :
                    n->op == "<"  ? "olt" : n->op == "<=" ? "ole" :
                    n->op == ">"  ? "ogt" : "oge";
                instr = std::string("fcmp ") + pred + " double " + lv.name + ", " + rv.name;
            } else {
                const char* pred =
                    n->op == "==" ? "eq"  : n->op == "!=" ? "ne"  :
                    n->op == "<"  ? "slt" : n->op == "<=" ? "sle" :
                    n->op == ">"  ? "sgt" : "sge";
                instr = std::string("icmp ") + pred + " i64 " + lv.name + ", " + rv.name;
            }
            emit_line(t + " = " + instr);
            return { t, "i1" };
        }

        // Arithmetic
        if (is_float) {
            const char* op =
                n->op == "+" ? "fadd" : n->op == "-" ? "fsub" :
                n->op == "*" ? "fmul" : n->op == "/" ? "fdiv" :
                n->op == "%" ? "frem" : "fadd";
            emit_line(t + " = " + op + " double " + lv.name + ", " + rv.name);
            return { t, "double" };
        }

        if (n->op == "**") {
            emit_line(t + " = call i64 @luz_powi(i64 " + lv.name + ", i64 " + rv.name + ")");
            needs_powi_ = true;
            return { t, "i64" };
        }

        const char* op =
            n->op == "+"  ? "add"  : n->op == "-"  ? "sub"  :
            n->op == "*"  ? "mul"  : n->op == "/"  ? "sdiv" :
            n->op == "//" ? "sdiv" : n->op == "%"  ? "srem" : "add";
        emit_line(t + " = " + op + " i64 " + lv.name + ", " + rv.name);
        return { t, "i64" };
    }

    Val emit_unary(HirUnaryOp* n) {
        Val v = emit_expr(n->operand.get());
        std::string t = tmp();
        if (n->op == "not") {
            emit_line(t + " = xor i1 " + v.name + ", 1");
            return { t, "i1" };
        }
        // unary minus
        if (v.type == "double") {
            emit_line(t + " = fneg double " + v.name);
            return { t, "double" };
        }
        emit_line(t + " = sub i64 0, " + v.name);
        return { t, "i64" };
    }

    // Coerce a Val to `target` LLVM type; emits conversion instructions.
    std::string coerce(const Val& v, const std::string& target) {
        if (v.type == target) return v.name;
        std::string t = tmp();
        if (v.type == "i1"  && target == "i64")
            emit_line(t + " = zext i1 " + v.name + " to i64");
        else if (v.type == "i64" && target == "i1")
            emit_line(t + " = icmp ne i64 " + v.name + ", 0");
        else if (v.type == "i64" && target == "double")
            emit_line(t + " = sitofp i64 " + v.name + " to double");
        else if (v.type == "double" && target == "i64")
            emit_line(t + " = fptosi double " + v.name + " to i64");
        else
            return v.name;  // unknown coercion — hope for the best
        return t;
    }

    std::string coerce_to_str(const Val& v) {
        if (v.type == "i8*") return v.name;
        std::string t = tmp();
        if (v.type == "i64")
            emit_line(t + " = call i8* @luz_to_str_int(i64 " + v.name + ")");
        else if (v.type == "double")
            emit_line(t + " = call i8* @luz_to_str_float(double " + v.name + ")");
        else if (v.type == "i1")
            emit_line(t + " = call i8* @luz_to_str_bool(i1 " + v.name + ")");
        else
            return v.name;
        return t;
    }

    Val coerce_to_str_val(const Val& v) {
        if (v.type == "i8*") return v;
        return { coerce_to_str(v), "i8*" };
    }

    // ── Dict helpers ──────────────────────────────────────────────────────────

    static std::string dict_setter(const std::string& llvm_t) {
        if (llvm_t == "i64"   ) return "luz_dict_set_int";
        if (llvm_t == "double") return "luz_dict_set_float";
        if (llvm_t == "i1"    ) return "luz_dict_set_bool";
        return "luz_dict_set_str";
    }

    static std::string dict_getter(const std::string& llvm_t) {
        if (llvm_t == "i64"   ) return "luz_dict_get_int";
        if (llvm_t == "double") return "luz_dict_get_float";
        if (llvm_t == "i1"    ) return "luz_dict_get_bool";
        return "luz_dict_get_str";
    }

    Val emit_dict(HirDict* n) {
        std::string t = tmp();
        emit_line(t + " = call i8* @luz_dict_new()");
        for (auto& p : n->pairs) {
            Val kv = emit_expr(p.key.get());
            Val vv = emit_expr(p.value.get());
            emit_line("call void @" + dict_setter(vv.type)
                      + "(i8* " + t + ", i8* " + kv.name
                      + ", " + vv.type + " " + vv.name + ")");
        }
        return { t, "i8*" };
    }

    Val emit_index_expr(HirIndex* n) {
        Val coll = emit_expr(n->collection.get());
        Val idx  = emit_expr(n->index.get());
        std::string result_t = llvm_type(n->type);
        if (result_t == "void") result_t = "i8*";
        std::string t = tmp();
        // string key → dict access; int key → list access (todo)
        if (idx.type == "i8*") {
            emit_line(t + " = call " + result_t + " @" + dict_getter(result_t)
                      + "(i8* " + coll.name + ", i8* " + idx.name + ")");
        } else {
            // list index — placeholder until lists are implemented
            emit_line(t + " = add i64 0, 0");
        }
        return { t, result_t };
    }

    void emit_index_store(HirIndexStore* n) {
        Val coll = emit_expr(n->collection.get());
        Val idx  = emit_expr(n->index.get());
        Val val  = emit_expr(n->value.get());
        if (idx.type == "i8*") {
            emit_line("call void @" + dict_setter(val.type)
                      + "(i8* " + coll.name + ", i8* " + idx.name
                      + ", " + val.type + " " + val.name + ")");
        }
        // list index store — todo
    }

    // Return the Luz source type of a HIR node (for dispatch decisions)
    std::string hir_type_of(HirNode* n) {
        if (n->kind == HirKind::Load) {
            auto* l = static_cast<HirLoad*>(n);
            if (!l->type.empty() && l->type != "unknown") return l->type;
            auto it = locals_.find(l->name);
            if (it != locals_.end()) return it->second.hir_type;
        }
        if (n->kind == HirKind::Dict)   return "dict";
        if (n->kind == HirKind::List)   return "list";
        if (n->kind == HirKind::Literal) {
            auto* lit = static_cast<HirLiteral*>(n);
            if (lit->vk == HirLiteral::ValKind::String) return "string";
        }
        return "";
    }

    // ── write() / print() builtin ─────────────────────────────────────────────

    void emit_write(const std::vector<HirNodePtr>& args) {
        if (args.empty()) return;
        Val v = emit_expr(args[0].get());

        if (v.type == "i64") {
            std::string fp = gep_str_const("@.fmt.int", 6);
            emit_line("call i32 (i8*, ...) @printf(i8* " + fp + ", i64 " + v.name + ")");
        } else if (v.type == "double") {
            std::string fp = gep_str_const("@.fmt.float", 4);
            emit_line("call i32 (i8*, ...) @printf(i8* " + fp + ", double " + v.name + ")");
        } else if (v.type == "i8*") {
            std::string fp = gep_str_const("@.fmt.str", 4);
            emit_line("call i32 (i8*, ...) @printf(i8* " + fp + ", i8* " + v.name + ")");
        } else if (v.type == "i1") {
            std::string t_lbl  = lbl("wr_true");
            std::string f_lbl  = lbl("wr_false");
            std::string af_lbl = lbl("wr_after");
            emit_line("br i1 " + v.name + ", label %" + t_lbl + ", label %" + f_lbl);
            *out_ << t_lbl << ":\n";
            std::string tp = gep_str_const("@.fmt.true", 6);
            emit_line("call i32 (i8*, ...) @printf(i8* " + tp + ")");
            emit_line("br label %" + af_lbl);
            *out_ << f_lbl << ":\n";
            std::string fp2 = gep_str_const("@.fmt.false", 7);
            emit_line("call i32 (i8*, ...) @printf(i8* " + fp2 + ")");
            emit_line("br label %" + af_lbl);
            *out_ << af_lbl << ":\n";
        } else {
            // Unrecognised type — fall back to printing as i64
            std::string fp = gep_str_const("@.fmt.int", 6);
            emit_line("call i32 (i8*, ...) @printf(i8* " + fp + ", i64 " + v.name + ")");
        }
    }

    Val emit_call(HirCall* n) {
        if (n->func == "write" || n->func == "print") {
            emit_write(n->args);
            return { "", "void" };
        }
        // Constructor call: ClassName(args...) → new dict + __init
        if (classes_.count(n->func)) {
            std::string obj = tmp();
            emit_line(obj + " = call i8* @luz_dict_new()");
            // Check if this class (or any parent) defines init
            std::string init_owner = resolve_method_class(n->func, "init");
            bool has_init = !init_owner.empty() && init_owner != n->func
                            ? true
                            : classes_.count(n->func) &&
                              [&]{ for(auto& m: classes_[n->func].methods) if(m=="init") return true; return false; }();
            // Simpler: just try to find init in hierarchy
            std::string owner_init = resolve_method_class(n->func, "init");
            if (classes_.count(owner_init) &&
                [&]{ for(auto& m: classes_[owner_init].methods) if(m=="init") return true; return false; }()) {
                std::string args_str = "i8* " + obj;
                for (auto& a : n->args) {
                    Val av = emit_expr(a.get());
                    args_str += ", " + av.type + " " + av.name;
                }
                emit_line("call void @" + owner_init + "__init(" + args_str + ")");
            }
            return { obj, "i8*" };
        }
        if (n->func == "to_str") {
            Val v = emit_expr(n->args[0].get());
            return coerce_to_str_val(v);
        }
        if (n->func == "len" && !n->args.empty()) {
            bool is_dict = hir_type_of(n->args[0].get()) == "dict";
            Val v = emit_expr(n->args[0].get());
            std::string t = tmp();
            if (is_dict)
                emit_line(t + " = call i64 @luz_dict_len(i8* " + v.name + ")");
            else
                emit_line(t + " = call i64 @luz_str_len(i8* " + v.name + ")");
            return { t, "i64" };
        }
        if (n->func == "contains" && n->args.size() >= 2) {
            bool is_dict = hir_type_of(n->args[0].get()) == "dict";
            Val obj    = emit_expr(n->args[0].get());
            Val needle = emit_expr(n->args[1].get());
            std::string t = tmp();
            if (is_dict)
                emit_line(t + " = call i1 @luz_dict_contains(i8* " + obj.name + ", i8* " + needle.name + ")");
            else
                emit_line(t + " = call i1 @luz_str_contains(i8* " + obj.name + ", i8* " + needle.name + ")");
            return { t, "i1" };
        }
        if (n->func == "remove" && n->args.size() >= 2) {
            Val obj = emit_expr(n->args[0].get());
            Val key = emit_expr(n->args[1].get());
            emit_line("call void @luz_dict_remove(i8* " + obj.name + ", i8* " + key.name + ")");
            return { "", "void" };
        }
        if (n->func == "exit") {
            Val code = n->args.empty() ? Val{"0","i64"} : emit_expr(n->args[0].get());
            std::string ec = coerce(code, "i64");
            std::string t  = tmp();
            emit_line(t + " = trunc i64 " + ec + " to i32");
            emit_line("call void @exit(i32 " + t + ")");
            emit_line("unreachable");
            *out_ << lbl("dead") << ":\n";
            return { "", "void" };
        }

        std::string ret_t = llvm_type(n->return_type);

        // Build argument list
        std::string arg_str;
        for (int i = 0; i < (int)n->args.size(); ++i) {
            Val av = emit_expr(n->args[i].get());
            if (i) arg_str += ", ";
            arg_str += av.type + " " + av.name;
        }

        if (ret_t == "void") {
            emit_line("call void @" + n->func + "(" + arg_str + ")");
            return { "", "void" };
        }
        std::string t = tmp();
        emit_line(t + " = call " + ret_t + " @" + n->func + "(" + arg_str + ")");
        return { t, ret_t };
    }

    Val emit_exprcall(HirExprCall* n) {
        // Calling an expression (lambda / first-class function) — limited support
        for (auto& a : n->args) emit_expr(a.get());
        return { "0", "i64" };
    }

    // ── Statement emission ────────────────────────────────────────────────────

    void emit_stmt(HirNode* n) {
        switch (n->kind) {
        case HirKind::Let:           emit_let(static_cast<HirLet*>(n));               break;
        case HirKind::Assign:        emit_assign(static_cast<HirAssign*>(n));         break;
        case HirKind::Call:          emit_call(static_cast<HirCall*>(n));             break;
        case HirKind::ExprCall:      emit_exprcall(static_cast<HirExprCall*>(n));     break;
        case HirKind::If:            emit_if_stmt(static_cast<HirIf*>(n));            break;
        case HirKind::While:         emit_while(static_cast<HirWhile*>(n));           break;
        case HirKind::Return:        emit_return(static_cast<HirReturn*>(n));         break;
        case HirKind::Break:         emit_break();                                    break;
        case HirKind::Continue:      emit_continue();                                 break;
        case HirKind::Alert:         emit_alert(static_cast<HirAlert*>(n));           break;
        case HirKind::AttemptRescue: emit_attempt(static_cast<HirAttemptRescue*>(n));break;
        case HirKind::FuncDef:       /* nested defs not supported */                  break;
        case HirKind::ClassDef:      /* emitted in emit_module, skip here */          break;
        case HirKind::StructDef:     /* structs not supported    */                   break;
        case HirKind::Import:        /* imports not supported    */                   break;
        case HirKind::IndexStore:    emit_index_store(static_cast<HirIndexStore*>(n));          break;
        case HirKind::FieldStore:    emit_field_store(static_cast<HirFieldStore*>(n));          break;
        case HirKind::ObjectCall:    emit_objectcall(static_cast<HirObjectCall*>(n));           break;
        case HirKind::Pass:          break;
        default:
            emit_expr(n);  // expression statement
            break;
        }
    }

    void emit_block(const HirBlock& blk) {
        for (auto& n : blk) emit_stmt(n.get());
    }

    void emit_let(HirLet* n) {
        std::string lt = llvm_type(n->type);
        if (lt == "void") lt = "i64";
        // User-defined class types are object pointers (i8*)
        if (lt == "i64" && classes_.count(n->type)) lt = "i8*";
        Val v = emit_expr(n->value.get());
        std::string sv = v.type != lt ? coerce(v, lt) : v.name;
        std::string ptr = "%" + n->name + ".addr";
        emit_line(ptr + " = alloca " + lt);
        emit_line("store " + lt + " " + sv + ", " + lt + "* " + ptr);
        locals_[n->name] = { ptr, lt, n->type };
    }

    void emit_assign(HirAssign* n) {
        Val v   = emit_expr(n->value.get());
        auto it = locals_.find(n->name);
        if (it == locals_.end()) {
            // First occurrence of an untyped assign — infer type from RHS
            std::string lt = (v.type == "void" || v.type.empty()) ? "i64" : v.type;
            std::string ptr = "%" + n->name + ".addr";
            emit_line(ptr + " = alloca " + lt);
            std::string ht = hir_type_of(n->value.get());
            locals_[n->name] = { ptr, lt, ht };
            it = locals_.find(n->name);
        }
        std::string sv = v.type != it->second.type ? coerce(v, it->second.type) : v.name;
        emit_line("store " + it->second.type + " " + sv
                  + ", " + it->second.type + "* " + it->second.ptr);
    }

    void emit_if_stmt(HirIf* n) {
        Val cond = emit_expr(n->cond.get());
        std::string cv = cond.type != "i1" ? coerce(cond, "i1") : cond.name;

        std::string then_lbl  = lbl("if_then");
        std::string else_lbl  = lbl("if_else");
        std::string after_lbl = lbl("if_after");
        bool has_else = !n->else_block.empty();

        emit_line("br i1 " + cv + ", label %" + then_lbl
                  + ", label %" + (has_else ? else_lbl : after_lbl));

        *out_ << then_lbl << ":\n";
        emit_block(n->then_block);
        emit_line("br label %" + after_lbl);

        if (has_else) {
            *out_ << else_lbl << ":\n";
            emit_block(n->else_block);
            emit_line("br label %" + after_lbl);
        }

        *out_ << after_lbl << ":\n";
    }

    void emit_while(HirWhile* n) {
        std::string cond_lbl = lbl("lp_cond");
        std::string body_lbl = lbl("lp_body");
        std::string exit_lbl = lbl("lp_exit");

        loop_stack_.push_back({ cond_lbl, exit_lbl });

        emit_line("br label %" + cond_lbl);
        *out_ << cond_lbl << ":\n";

        Val cond = emit_expr(n->cond.get());
        std::string cv = cond.type != "i1" ? coerce(cond, "i1") : cond.name;
        emit_line("br i1 " + cv + ", label %" + body_lbl + ", label %" + exit_lbl);

        *out_ << body_lbl << ":\n";
        emit_block(n->body);
        emit_line("br label %" + cond_lbl);

        *out_ << exit_lbl << ":\n";
        loop_stack_.pop_back();
    }

    void emit_return(HirReturn* n) {
        if (!n->value || current_ret_type_ == "void") {
            if (current_ret_type_ == "void")
                emit_line("ret void");
            else
                emit_line("ret " + current_ret_type_ + " 0");
        } else {
            Val v  = emit_expr(n->value.get());
            std::string rv = v.type != current_ret_type_
                             ? coerce(v, current_ret_type_) : v.name;
            emit_line("ret " + current_ret_type_ + " " + rv);
        }
        // Dead block after ret (required for LLVM IR validity)
        *out_ << lbl("dead") << ":\n";
    }

    void emit_break() {
        if (loop_stack_.empty()) return;
        emit_line("br label %" + loop_stack_.back().exit_lbl);
        *out_ << lbl("dead") << ":\n";
    }

    void emit_continue() {
        if (loop_stack_.empty()) return;
        emit_line("br label %" + loop_stack_.back().cond_lbl);
        *out_ << lbl("dead") << ":\n";
    }

    void emit_alert(HirAlert* n) {
        Val v = emit_expr(n->value.get());
        if (v.type == "i8*") {
            std::string fp = gep_str_const("@.fmt.str", 4);
            emit_line("call i32 (i8*, ...) @printf(i8* " + fp + ", i8* " + v.name + ")");
        } else {
            // Print numeric alert value
            std::string fp = gep_str_const("@.fmt.int", 6);
            emit_line("call i32 (i8*, ...) @printf(i8* " + fp + ", i64 " + v.name + ")");
        }
        emit_line("call void @exit(i32 1)");
        emit_line("unreachable");
        *out_ << lbl("dead") << ":\n";
    }

    void emit_attempt(HirAttemptRescue* n) {
        // No LLVM exceptions — emit try body; rescue is unreachable; finally always runs.
        emit_block(n->try_block);
        emit_block(n->finally_block);
    }

    // ── Function definition ───────────────────────────────────────────────────

    void emit_func(HirFuncDef* n) {
        // Save outer state
        auto saved_locals = locals_;
        auto saved_ret    = current_ret_type_;
        auto saved_loops  = loop_stack_;
        int  saved_tmp    = tmp_id_;
        int  saved_lbl    = label_id_;
        std::ostringstream saved_body;
        saved_body << body_buf_.str();

        reset_counters();

        std::string ret_t = llvm_type(n->return_type);
        current_ret_type_ = ret_t;

        // Build parameter list
        std::string params;
        for (int i = 0; i < (int)n->params.size(); ++i) {
            if (i) params += ", ";
            params += llvm_type(n->params[i].type) + " %" + n->params[i].name + ".in";
        }

        final_out_ << "\ndefine " << ret_t << " @" << n->name
                   << "(" << params << ") {\n"
                   << "entry:\n";

        // Spill params to alloca so they're mutable
        for (auto& p : n->params) {
            std::string pt  = llvm_type(p.type);
            std::string ptr = "%" + p.name + ".addr";
            emit_line(ptr + " = alloca " + pt);
            emit_line("store " + pt + " %" + p.name + ".in, " + pt + "* " + ptr);
            locals_[p.name] = { ptr, pt };
        }

        emit_block(n->body);

        // Ensure every path ends with a terminator
        if      (ret_t == "void"  ) emit_line("ret void");
        else if (ret_t == "i64"   ) emit_line("ret i64 0");
        else if (ret_t == "double") emit_line("ret double 0.0");
        else if (ret_t == "i1"    ) emit_line("ret i1 0");
        else                        emit_line("ret " + ret_t + " undef");

        final_out_ << body_buf_.str() << "}\n";

        // Restore outer state
        locals_           = std::move(saved_locals);
        current_ret_type_ = saved_ret;
        loop_stack_       = std::move(saved_loops);
        tmp_id_           = saved_tmp;
        label_id_         = saved_lbl;
        body_buf_.str(saved_body.str());
        body_buf_.clear();
        // Re-seek to end
        body_buf_.seekp(0, std::ios_base::end);
        out_ = &body_buf_;
    }

    // ── Class support ─────────────────────────────────────────────────────────

    // Walk up the inheritance chain to find which class defines a method.
    std::string resolve_method_class(const std::string& class_name,
                                     const std::string& method) {
        std::string cur = class_name;
        while (!cur.empty()) {
            auto it = classes_.find(cur);
            if (it == classes_.end()) break;
            for (auto& m : it->second.methods)
                if (m == method) return cur;
            cur = it->second.parent;
        }
        return class_name;
    }

    void emit_class(HirClassDef* cls) {
        for (auto& m : cls->methods) {
            if (m->kind == HirKind::FuncDef)
                emit_class_method(cls->name, static_cast<HirFuncDef*>(m.get()));
        }
    }

    void emit_class_method(const std::string& class_name, HirFuncDef* n) {
        // Save outer state
        auto saved_locals = locals_;
        auto saved_ret    = current_ret_type_;
        auto saved_loops  = loop_stack_;
        int  saved_tmp    = tmp_id_;
        int  saved_lbl    = label_id_;
        std::ostringstream saved_body;
        saved_body << body_buf_.str();

        reset_counters();

        std::string ret_t = llvm_type(n->return_type);
        // Methods with no explicit return type are void
        if (n->return_type.empty() || n->return_type == "unknown") ret_t = "void";
        current_ret_type_ = ret_t;

        // self + explicit params
        std::string params = "i8* %self.in";
        for (auto& p : n->params)
            params += ", " + llvm_type(p.type) + " %" + p.name + ".in";

        final_out_ << "\ndefine " << ret_t << " @"
                   << class_name << "__" << n->name
                   << "(" << params << ") {\n"
                   << "entry:\n";

        // Spill self — hir_type = class name so field lookups work
        emit_line("%self.addr = alloca i8*");
        emit_line("store i8* %self.in, i8** %self.addr");
        locals_["self"] = { "%self.addr", "i8*", class_name };

        // Spill explicit params
        for (auto& p : n->params) {
            std::string pt  = llvm_type(p.type);
            std::string ptr = "%" + p.name + ".addr";
            emit_line(ptr + " = alloca " + pt);
            emit_line("store " + pt + " %" + p.name + ".in, " + pt + "* " + ptr);
            locals_[p.name] = { ptr, pt, p.type };
        }

        emit_block(n->body);

        // Trailing terminator (dead code guard)
        if      (ret_t == "void"  ) emit_line("ret void");
        else if (ret_t == "i64"   ) emit_line("ret i64 0");
        else if (ret_t == "double") emit_line("ret double 0.0");
        else if (ret_t == "i1"    ) emit_line("ret i1 0");
        else                        emit_line("ret i8* null");

        final_out_ << body_buf_.str() << "}\n";

        // Restore outer state
        locals_           = std::move(saved_locals);
        current_ret_type_ = saved_ret;
        loop_stack_       = std::move(saved_loops);
        tmp_id_           = saved_tmp;
        label_id_         = saved_lbl;
        body_buf_.str(saved_body.str());
        body_buf_.clear();
        body_buf_.seekp(0, std::ios_base::end);
        out_ = &body_buf_;
    }

    Val emit_field_load(HirFieldLoad* n) {
        Val obj = emit_expr(n->obj.get());
        std::string result_t = llvm_type(n->type);
        // "unknown" types: look up from class field registry
        if (result_t == "i64" && (n->type.empty() || n->type == "unknown")) {
            std::string class_name = hir_type_of(n->obj.get());
            result_t = resolve_field_type(class_name, n->field);
        }
        if (result_t == "void") result_t = "i8*";
        int id = intern(n->field);
        std::string key = gep_pool_str(id);
        std::string t = tmp();
        emit_line(t + " = call " + result_t + " @" + dict_getter(result_t)
                  + "(i8* " + obj.name + ", i8* " + key + ")");
        return { t, result_t };
    }

    void emit_field_store(HirFieldStore* n) {
        Val obj = emit_expr(n->obj.get());
        Val val = emit_expr(n->value.get());
        int id  = intern(n->field);
        std::string key = gep_pool_str(id);
        emit_line("call void @" + dict_setter(val.type)
                  + "(i8* " + obj.name + ", i8* " + key
                  + ", " + val.type + " " + val.name + ")");
    }

    Val emit_objectcall(HirObjectCall* n) {
        Val obj = emit_expr(n->obj.get());
        std::string class_name = hir_type_of(n->obj.get());
        std::string owner = resolve_method_class(class_name, n->method);
        std::string ret_t = llvm_type(n->return_type);
        if (n->return_type.empty() || n->return_type == "unknown") {
            // Look up actual return type from class registry
            auto cit = classes_.find(owner);
            if (cit != classes_.end()) {
                auto rit = cit->second.method_ret_types.find(n->method);
                ret_t = (rit != cit->second.method_ret_types.end()) ? rit->second : "void";
            } else {
                ret_t = "void";
            }
        }

        std::string arg_str = "i8* " + obj.name;
        for (auto& a : n->args) {
            Val av = emit_expr(a.get());
            arg_str += ", " + av.type + " " + av.name;
        }

        if (ret_t == "void") {
            emit_line("call void @" + owner + "__" + n->method + "(" + arg_str + ")");
            return { "", "void" };
        }
        std::string t = tmp();
        emit_line(t + " = call " + ret_t + " @" + owner + "__" + n->method
                  + "(" + arg_str + ")");
        return { t, ret_t };
    }

    // ── luz_powi helper ───────────────────────────────────────────────────────

    void emit_powi_helper() {
        final_out_ <<
            "\ndefine i64 @luz_powi(i64 %base, i64 %exp) {\n"
            "entry:\n"
            "  %result.addr = alloca i64\n"
            "  %base2.addr  = alloca i64\n"
            "  %exp2.addr   = alloca i64\n"
            "  store i64 1,     i64* %result.addr\n"
            "  store i64 %base, i64* %base2.addr\n"
            "  store i64 %exp,  i64* %exp2.addr\n"
            "  br label %pw_cond\n"
            "pw_cond:\n"
            "  %e0 = load i64, i64* %exp2.addr\n"
            "  %c0 = icmp sgt i64 %e0, 0\n"
            "  br i1 %c0, label %pw_body, label %pw_exit\n"
            "pw_body:\n"
            "  %r0 = load i64, i64* %result.addr\n"
            "  %b0 = load i64, i64* %base2.addr\n"
            "  %r1 = mul i64 %r0, %b0\n"
            "  store i64 %r1, i64* %result.addr\n"
            "  %e1 = load i64, i64* %exp2.addr\n"
            "  %e2 = sub i64 %e1, 1\n"
            "  store i64 %e2, i64* %exp2.addr\n"
            "  br label %pw_cond\n"
            "pw_exit:\n"
            "  %res = load i64, i64* %result.addr\n"
            "  ret i64 %res\n"
            "}\n";
    }
};

}  // namespace

// ── Public API ────────────────────────────────────────────────────────────────

void emit_llvm_ir(std::ostream& out,
                  const HirBlock& program,
                  const std::string& filename) {
    CodeGen cg(out);
    cg.emit_module(program, filename);
}

}  // namespace luz
