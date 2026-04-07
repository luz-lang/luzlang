# codegen.py — LLVM IR code generator for Luz.
#
# Lowers HIR nodes (from luz/hir.py) to LLVM IR via llvmlite, then
# optionally compiles to a native object file or executable by linking
# against the C runtime (luz/runtime/).
#
# All Luz values are represented uniformly as `luz_value_t`, which maps
# to the LLVM struct type {i32 tag, i32 pad, i64 data} (16 bytes,
# matching the C layout on 64-bit targets).
#
# ABI note: struct-by-value calling conventions differ between the
# System V AMD64 ABI (Linux/macOS) and the Windows x64 ABI.  The
# generated IR targets the host triple via llvmlite; on Windows with
# MinGW/GCC the System V rules apply.  When linking with MSVC-compiled
# objects, use the pointer-based wrappers in luz_rt_ops.c instead.
#
# Usage:
#   from luz.codegen import LLVMCodeGen
#   gen = LLVMCodeGen()
#   gen.gen_program(hir_nodes)
#   print(gen.module)                   # emit LLVM IR text
#   gen.compile_to_object("out.o")      # compile to object file
#   gen.compile_to_exe("out")           # link into executable

from __future__ import annotations

try:
    import llvmlite.ir as ir
    import llvmlite.binding as llvm
    _HAS_LLVMLITE = True
except ImportError:  # pragma: no cover
    _HAS_LLVMLITE = False

import struct as _struct
from typing import Optional

from .hir import (
    HirLiteral, HirLoad, HirLet, HirAssign, HirBinOp, HirUnaryOp,
    HirCall, HirExprCall, HirBlock, HirIf, HirWhile, HirReturn,
    HirBreak, HirContinue, HirFuncDef, HirClassDef, HirStructDef,
    HirFieldLoad, HirFieldStore, HirIndex, HirIndexStore,
    HirList, HirDict, HirImport, HirAttemptRescue, HirAlert, HirPass,
)


class LLVMCodeGenError(Exception):
    pass


class LLVMCodeGen:
    """LLVM IR code generator for the Luz compiler backend."""

    # luz_type_t enum values (must match luz_runtime.h)
    TAG_NULL     = 0
    TAG_BOOL     = 1
    TAG_INT      = 2
    TAG_FLOAT    = 3
    TAG_STRING   = 4
    TAG_LIST     = 5
    TAG_DICT     = 6
    TAG_OBJECT   = 7
    TAG_FUNCTION = 8

    def __init__(self, module_name: str = "luz_program"):
        if not _HAS_LLVMLITE:
            raise LLVMCodeGenError(
                "llvmlite is not installed. Run: pip install llvmlite"
            )

        self.module = ir.Module(name=module_name)
        triple = llvm.get_default_triple()
        # On Windows, llvmlite defaults to x86_64-pc-windows-msvc (MSVC ABI).
        # The C runtime is compiled with MinGW (GNU ABI), so we force the GNU
        # triple to avoid struct-return ABI mismatches.
        if "windows-msvc" in triple:
            triple = triple.replace("windows-msvc", "windows-gnu")
        self.module.triple = triple

        # Primitive LLVM types
        self.i1   = ir.IntType(1)
        self.i8   = ir.IntType(8)
        self.i32  = ir.IntType(32)
        self.i64  = ir.IntType(64)
        self.f64  = ir.DoubleType()
        self.void = ir.VoidType()
        self.ptr  = ir.PointerType(ir.IntType(8))   # i8* as opaque pointer

        # luz_value_t = {i32 tag, i32 pad, i64 data}  (16 bytes)
        self.val_t = ir.LiteralStructType([self.i32, self.i32, self.i64])

        # Builder / function state
        self._builder: Optional[ir.IRBuilder]  = None
        self._func:    Optional[ir.Function]   = None
        self._scope_stack: list[dict]          = []
        self._break_bb:    Optional[ir.Block]  = None
        self._continue_bb: Optional[ir.Block]  = None
        self._user_funcs:  dict[str, ir.Function] = {}
        self._runtime:     dict[str, ir.Function] = {}

        self._declare_runtime()

    # ── Constant constructors ────────────────────────────────────────────────

    def _null_val(self) -> ir.Constant:
        return ir.Constant(self.val_t, [self.TAG_NULL, 0, 0])

    def _int_val(self, n: int) -> ir.Constant:
        return ir.Constant(self.val_t, [self.TAG_INT, 0, n & 0xFFFF_FFFF_FFFF_FFFF])

    def _float_val(self, f: float) -> ir.Constant:
        bits = _struct.unpack("Q", _struct.pack("d", f))[0]
        return ir.Constant(self.val_t, [self.TAG_FLOAT, 0, bits])

    def _bool_val(self, b: bool) -> ir.Constant:
        return ir.Constant(self.val_t, [self.TAG_BOOL, 0, int(b)])

    # Build a luz_value_t at runtime from a tag (i32) and data (i64).
    def _build_val(self, tag: ir.Value, data: ir.Value) -> ir.Value:
        pad  = ir.Constant(self.i32, 0)
        s    = ir.Constant(self.val_t, ir.Undefined)
        s    = self._builder.insert_value(s, tag,  0)
        s    = self._builder.insert_value(s, pad,  1)
        s    = self._builder.insert_value(s, data, 2)
        return s

    # ── Runtime function declarations ────────────────────────────────────────

    def _fn(self, name: str, ret, *args) -> ir.Function:
        ftype = ir.FunctionType(ret, list(args))
        fn = ir.Function(self.module, ftype, name=name)
        fn.linkage = "external"
        self._runtime[name] = fn
        return fn

    def _declare_runtime(self):
        vt = self.val_t
        p  = self.ptr
        v  = self.void

        # I/O
        self._fn("luz_builtin_write",    v,   vt)
        self._fn("luz_builtin_listen",   vt)

        # Type conversion
        self._fn("luz_builtin_to_int",   vt, vt)
        self._fn("luz_builtin_to_float", vt, vt)
        self._fn("luz_builtin_to_str",   vt, vt)
        self._fn("luz_builtin_to_bool",  vt, vt)

        # Introspection
        self._fn("luz_builtin_typeof",   vt, vt)
        self._fn("luz_builtin_len",      vt, vt)

        # Math builtins
        self._fn("luz_builtin_abs",    vt, vt)
        self._fn("luz_builtin_sqrt",   vt, vt)
        self._fn("luz_builtin_floor",  vt, vt)
        self._fn("luz_builtin_ceil",   vt, vt)
        self._fn("luz_builtin_round",  vt, vt)
        self._fn("luz_builtin_exp",    vt, vt)
        self._fn("luz_builtin_ln",     vt, vt)
        self._fn("luz_builtin_sin",    vt, vt)
        self._fn("luz_builtin_cos",    vt, vt)
        self._fn("luz_builtin_tan",    vt, vt)
        self._fn("luz_builtin_min",    vt, vt, vt)
        self._fn("luz_builtin_max",    vt, vt, vt)
        self._fn("luz_builtin_clamp",  vt, vt, vt, vt)

        # List builtins
        self._fn("luz_builtin_append",  v,  vt, vt)
        self._fn("luz_builtin_pop",     vt, vt)
        self._fn("luz_builtin_insert",  v,  vt, vt, vt)
        self._fn("luz_builtin_range",   vt, vt, vt, vt)
        self._fn("luz_builtin_sum",     vt, vt)
        self._fn("luz_builtin_any",     vt, vt)
        self._fn("luz_builtin_all",     vt, vt)
        self._fn("luz_builtin_reverse", vt, vt)

        # String builtins
        self._fn("luz_builtin_split",       vt, vt, vt)
        self._fn("luz_builtin_join",        vt, vt, vt)
        self._fn("luz_builtin_trim",        vt, vt)
        self._fn("luz_builtin_upper",       vt, vt)
        self._fn("luz_builtin_lower",       vt, vt)
        self._fn("luz_builtin_find",        vt, vt, vt)
        self._fn("luz_builtin_replace",     vt, vt, vt, vt)
        self._fn("luz_builtin_starts_with", vt, vt, vt)
        self._fn("luz_builtin_ends_with",   vt, vt, vt)

        # Dict builtins
        self._fn("luz_builtin_keys",   vt, vt)
        self._fn("luz_builtin_values", vt, vt)
        self._fn("luz_builtin_remove", v,  vt, vt)

        # Alert / exceptions
        self._fn("luz_builtin_alert", v,  vt)
        self._fn("luz_raise",         v,  vt)
        self._fn("luz_exc_push",      v,  p)
        self._fn("luz_exc_pop",       v)

        # Dynamic dispatch helpers (implemented in luz_rt_ops.c)
        for op in ("add", "sub", "mul", "div", "floordiv", "mod", "pow",
                   "eq", "ne", "lt", "le", "gt", "ge", "and_", "or_",
                   "in_", "not_in"):
            self._fn(f"luz_rt_{op}", vt, vt, vt)
        self._fn("luz_rt_neg",      vt, vt)
        self._fn("luz_rt_not",      vt, vt)
        self._fn("luz_rt_truthy",   self.i1, vt)
        self._fn("luz_rt_getindex", vt, vt, vt)
        self._fn("luz_rt_setindex", v,  vt, vt, vt)
        self._fn("luz_rt_getfield", vt, vt, p)
        self._fn("luz_rt_setfield", v,  vt, p, vt)
        self._fn("luz_rt_make_list", vt, self.i32)
        self._fn("luz_rt_make_dict", vt, self.i32)
        self._fn("luz_rt_str_literal", vt, p, self.i64)

    def _rt(self, name: str) -> ir.Function:
        return self._runtime[name]

    # ── Scope management ─────────────────────────────────────────────────────

    def _push_scope(self):
        self._scope_stack.append({})

    def _pop_scope(self):
        self._scope_stack.pop()

    def _define(self, name: str, alloca: ir.AllocaInstr):
        self._scope_stack[-1][name] = alloca

    def _lookup(self, name: str) -> Optional[ir.AllocaInstr]:
        for scope in reversed(self._scope_stack):
            if name in scope:
                return scope[name]
        return None

    def _alloca(self, name: str = "") -> ir.AllocaInstr:
        """Allocate a luz_value_t slot on the stack."""
        return self._builder.alloca(self.val_t, name=name)

    # ── Public API ────────────────────────────────────────────────────────────

    def gen_program(self, hir_nodes: list) -> ir.Function:
        """Lower a top-level HIR list into a C-compatible `main` function."""
        ftype   = ir.FunctionType(self.i32, [])
        main_fn = ir.Function(self.module, ftype, name="main")
        entry   = main_fn.append_basic_block("entry")

        self._func    = main_fn
        self._builder = ir.IRBuilder(entry)
        self._push_scope()

        for node in hir_nodes:
            if self._builder.block.is_terminated:
                break
            # Top-level function / class defs: generate without emitting code
            # into main's basic block.
            if isinstance(node, (HirFuncDef, HirClassDef, HirStructDef)):
                self.gen(node)
            else:
                self.gen(node)

        if not self._builder.block.is_terminated:
            self._builder.ret(ir.Constant(self.i32, 0))

        self._pop_scope()
        return main_fn

    def gen(self, node) -> Optional[ir.Value]:
        """Dispatch HIR node to its generator method."""
        if node is None:
            return self._null_val()
        method = f"_gen_{type(node).__name__}"
        return getattr(self, method, self._gen_unknown)(node)

    def _gen_unknown(self, _node) -> ir.Value:
        return self._null_val()

    # ── Literals ──────────────────────────────────────────────────────────────

    def _gen_HirLiteral(self, node: HirLiteral) -> ir.Value:
        v = node.value
        if v is None:
            return self._null_val()
        if isinstance(v, bool):
            return self._bool_val(v)
        if isinstance(v, int):
            return self._int_val(v)
        if isinstance(v, float):
            return self._float_val(v)
        if isinstance(v, str):
            b      = v.encode("utf-8")
            arr_ty = ir.ArrayType(self.i8, len(b) + 1)
            g      = ir.GlobalVariable(self.module, arr_ty,
                                       name=self.module.get_unique_name("str"))
            g.linkage        = "private"
            g.global_constant = True
            g.initializer    = ir.Constant(arr_ty, bytearray(b + b"\0"))
            data_ptr = self._builder.bitcast(g, self.ptr)
            length   = ir.Constant(self.i64, len(b))
            return self._builder.call(self._rt("luz_rt_str_literal"),
                                      [data_ptr, length])
        return self._null_val()

    # ── Variables ─────────────────────────────────────────────────────────────

    def _gen_HirLet(self, node: HirLet) -> None:
        alloca = self._alloca(node.name)
        self._define(node.name, alloca)
        val = self.gen(node.value)
        if val is not None:
            self._builder.store(val, alloca)

    def _gen_HirAssign(self, node: HirAssign) -> None:
        alloca = self._lookup(node.name)
        if alloca is None:
            alloca = self._alloca(node.name)
            self._define(node.name, alloca)
        val = self.gen(node.value)
        if val is not None:
            self._builder.store(val, alloca)

    def _gen_HirLoad(self, node: HirLoad) -> ir.Value:
        alloca = self._lookup(node.name)
        if alloca is None:
            return self._null_val()
        return self._builder.load(alloca, name=node.name)

    # ── Operators ─────────────────────────────────────────────────────────────

    _BINOP_RT = {
        "+":    "luz_rt_add",
        "-":    "luz_rt_sub",
        "*":    "luz_rt_mul",
        "/":    "luz_rt_div",
        "//":   "luz_rt_floordiv",
        "%":    "luz_rt_mod",
        "**":   "luz_rt_pow",
        "==":   "luz_rt_eq",
        "!=":   "luz_rt_ne",
        "<":    "luz_rt_lt",
        "<=":   "luz_rt_le",
        ">":    "luz_rt_gt",
        ">=":   "luz_rt_ge",
        "and":  "luz_rt_and_",
        "or":   "luz_rt_or_",
        "in":   "luz_rt_in_",
        "not in": "luz_rt_not_in",
    }

    def _gen_HirBinOp(self, node: HirBinOp) -> ir.Value:
        left  = self.gen(node.left)
        right = self.gen(node.right)
        rt    = self._BINOP_RT.get(node.op)
        if rt:
            return self._builder.call(self._rt(rt), [left, right])
        return self._null_val()

    def _gen_HirUnaryOp(self, node: HirUnaryOp) -> ir.Value:
        operand = self.gen(node.operand)
        if node.op == "-":
            return self._builder.call(self._rt("luz_rt_neg"), [operand])
        if node.op == "not":
            return self._builder.call(self._rt("luz_rt_not"), [operand])
        return operand

    # ── Control flow ──────────────────────────────────────────────────────────

    def _gen_HirBlock(self, node: HirBlock) -> None:
        self._push_scope()
        for stmt in node.stmts:
            if self._builder.block.is_terminated:
                break
            self.gen(stmt)
        self._pop_scope()

    def _gen_HirIf(self, node: HirIf) -> None:
        cond_val = self.gen(node.cond)
        cond_i1  = self._builder.call(self._rt("luz_rt_truthy"), [cond_val])

        fn       = self._func
        then_bb  = fn.append_basic_block("if.then")
        merge_bb = fn.append_basic_block("if.merge")

        if node.else_block:
            else_bb = fn.append_basic_block("if.else")
            self._builder.cbranch(cond_i1, then_bb, else_bb)
        else:
            self._builder.cbranch(cond_i1, then_bb, merge_bb)

        # then branch
        self._builder.position_at_end(then_bb)
        self._gen_HirBlock(node.then_block)
        if not self._builder.block.is_terminated:
            self._builder.branch(merge_bb)

        # else branch
        if node.else_block:
            self._builder.position_at_end(else_bb)
            self._gen_HirBlock(node.else_block)
            if not self._builder.block.is_terminated:
                self._builder.branch(merge_bb)

        self._builder.position_at_end(merge_bb)

    def _gen_HirWhile(self, node: HirWhile) -> None:
        fn      = self._func
        cond_bb = fn.append_basic_block("while.cond")
        body_bb = fn.append_basic_block("while.body")
        exit_bb = fn.append_basic_block("while.exit")

        self._builder.branch(cond_bb)

        prev_break    = self._break_bb
        prev_continue = self._continue_bb
        self._break_bb    = exit_bb
        self._continue_bb = cond_bb

        # condition block
        self._builder.position_at_end(cond_bb)
        cond_val = self.gen(node.cond)
        cond_i1  = self._builder.call(self._rt("luz_rt_truthy"), [cond_val])
        self._builder.cbranch(cond_i1, body_bb, exit_bb)

        # body block
        self._builder.position_at_end(body_bb)
        self._gen_HirBlock(node.block)
        if not self._builder.block.is_terminated:
            self._builder.branch(cond_bb)

        self._builder.position_at_end(exit_bb)

        self._break_bb    = prev_break
        self._continue_bb = prev_continue

    def _gen_HirReturn(self, node: HirReturn) -> None:
        val = self.gen(node.value) if node.value is not None else self._null_val()
        # main returns i32; all other functions return val_t
        if self._func.function_type.return_type == self.i32:
            # Extract the integer data field as the exit code
            data = self._builder.extract_value(val, 2)
            code = self._builder.trunc(data, self.i32)
            self._builder.ret(code)
        else:
            self._builder.ret(val)

    def _gen_HirBreak(self, _node) -> None:
        if self._break_bb:
            self._builder.branch(self._break_bb)

    def _gen_HirContinue(self, _node) -> None:
        if self._continue_bb:
            self._builder.branch(self._continue_bb)

    def _gen_HirPass(self, _node) -> None:
        pass

    # ── Function definitions ──────────────────────────────────────────────────

    def _gen_HirFuncDef(self, node: HirFuncDef) -> ir.Function:
        return self._compile_func(node)

    def _compile_func(self, node: HirFuncDef) -> ir.Function:
        param_types = [self.val_t] * len(node.params)
        ftype       = ir.FunctionType(self.val_t, param_types)
        name        = node.name or self.module.get_unique_name("lambda")
        fn          = ir.Function(self.module, ftype, name=name)
        if node.name:
            self._user_funcs[node.name] = fn

        entry = fn.append_basic_block("entry")

        # Save outer state
        saved = (self._builder, self._func, self._scope_stack,
                 self._break_bb, self._continue_bb)

        self._func          = fn
        self._builder       = ir.IRBuilder(entry)
        self._scope_stack   = [{}]
        self._break_bb      = None
        self._continue_bb   = None

        # Bind parameters
        for (pname, _), arg in zip(node.params, fn.args):
            arg.name = pname
            slot     = self._alloca(pname)
            self._builder.store(arg, slot)
            self._scope_stack[-1][pname] = slot

        # Generate body
        self._gen_HirBlock(node.body)
        if not self._builder.block.is_terminated:
            self._builder.ret(self._null_val())

        # Restore outer state
        (self._builder, self._func, self._scope_stack,
         self._break_bb, self._continue_bb) = saved

        return fn

    # ── Calls ─────────────────────────────────────────────────────────────────

    _BUILTIN_RT: dict[str, str] = {
        "write":       "luz_builtin_write",
        "listen":      "luz_builtin_listen",
        "to_int":      "luz_builtin_to_int",
        "to_float":    "luz_builtin_to_float",
        "to_str":      "luz_builtin_to_str",
        "to_bool":     "luz_builtin_to_bool",
        "typeof":      "luz_builtin_typeof",
        "len":         "luz_builtin_len",
        "abs":         "luz_builtin_abs",
        "sqrt":        "luz_builtin_sqrt",
        "floor":       "luz_builtin_floor",
        "ceil":        "luz_builtin_ceil",
        "round":       "luz_builtin_round",
        "exp":         "luz_builtin_exp",
        "ln":          "luz_builtin_ln",
        "sin":         "luz_builtin_sin",
        "cos":         "luz_builtin_cos",
        "tan":         "luz_builtin_tan",
        "min":         "luz_builtin_min",
        "max":         "luz_builtin_max",
        "clamp":       "luz_builtin_clamp",
        "append":      "luz_builtin_append",
        "pop":         "luz_builtin_pop",
        "insert":      "luz_builtin_insert",
        "range":       "luz_builtin_range",
        "sum":         "luz_builtin_sum",
        "any":         "luz_builtin_any",
        "all":         "luz_builtin_all",
        "reverse":     "luz_builtin_reverse",
        "split":       "luz_builtin_split",
        "join":        "luz_builtin_join",
        "trim":        "luz_builtin_trim",
        "upper":       "luz_builtin_upper",
        "lower":       "luz_builtin_lower",
        "find":        "luz_builtin_find",
        "replace":     "luz_builtin_replace",
        "starts_with": "luz_builtin_starts_with",
        "ends_with":   "luz_builtin_ends_with",
        "keys":        "luz_builtin_keys",
        "values":      "luz_builtin_values",
        "remove":      "luz_builtin_remove",
        "alert":       "luz_builtin_alert",
        "__slice":     "luz_rt_slice",
    }

    def _gen_HirCall(self, node: HirCall) -> ir.Value:
        args = [self.gen(a) for a in node.args]

        rt_name = self._BUILTIN_RT.get(node.func)
        if rt_name and rt_name in self._runtime:
            fn     = self._rt(rt_name)
            result = self._builder.call(fn, args)
            return result if fn.function_type.return_type != self.void else self._null_val()

        if node.func in self._user_funcs:
            return self._builder.call(self._user_funcs[node.func], args)

        return self._null_val()

    def _gen_HirExprCall(self, node: HirExprCall) -> ir.Value:
        # Indirect calls (function stored in a variable) require a trampoline;
        # not yet supported — callee is discarded, return null.
        return self._null_val()

    # ── Collections ───────────────────────────────────────────────────────────

    def _gen_HirList(self, node: HirList) -> ir.Value:
        n   = ir.Constant(self.i32, len(node.elements))
        lst = self._builder.call(self._rt("luz_rt_make_list"), [n])
        for elem in node.elements:
            val = self.gen(elem)
            self._builder.call(self._rt("luz_builtin_append"), [lst, val])
        return lst

    def _gen_HirDict(self, node: HirDict) -> ir.Value:
        n = ir.Constant(self.i32, len(node.pairs))
        d = self._builder.call(self._rt("luz_rt_make_dict"), [n])
        for k_node, v_node in node.pairs:
            k = self.gen(k_node)
            v = self.gen(v_node)
            self._builder.call(self._rt("luz_rt_setindex"), [d, k, v])
        return d

    # ── Field / index access ──────────────────────────────────────────────────

    def _gen_HirFieldLoad(self, node: HirFieldLoad) -> ir.Value:
        obj  = self.gen(node.obj)
        name = self._cstr(node.field)
        return self._builder.call(self._rt("luz_rt_getfield"), [obj, name])

    def _gen_HirFieldStore(self, node: HirFieldStore) -> None:
        obj   = self.gen(node.obj)
        name  = self._cstr(node.field)
        value = self.gen(node.value)
        self._builder.call(self._rt("luz_rt_setfield"), [obj, name, value])

    def _gen_HirIndex(self, node: HirIndex) -> ir.Value:
        coll  = self.gen(node.collection)
        index = self.gen(node.index)
        return self._builder.call(self._rt("luz_rt_getindex"), [coll, index])

    def _gen_HirIndexStore(self, node: HirIndexStore) -> None:
        coll  = self.gen(node.collection)
        index = self.gen(node.index)
        value = self.gen(node.value)
        self._builder.call(self._rt("luz_rt_setindex"), [coll, index, value])

    def _cstr(self, s: str) -> ir.Value:
        """Intern a C string as a private global and return an i8* to it."""
        b      = s.encode("utf-8") + b"\0"
        arr_ty = ir.ArrayType(self.i8, len(b))
        g      = ir.GlobalVariable(self.module, arr_ty,
                                   name=self.module.get_unique_name("cstr"))
        g.linkage        = "private"
        g.global_constant = True
        g.initializer    = ir.Constant(arr_ty, bytearray(b))
        return self._builder.bitcast(g, self.ptr)

    # ── Exception handling ────────────────────────────────────────────────────

    def _gen_HirAlert(self, node: HirAlert) -> None:
        val = self.gen(node.value)
        self._builder.call(self._rt("luz_raise"), [val])
        self._builder.unreachable()

    def _gen_HirAttemptRescue(self, node: HirAttemptRescue) -> None:
        # Full setjmp/longjmp integration is deferred (requires alloca of
        # luz_exc_frame_t and inline setjmp).  For now, emit try body
        # unconditionally; rescue body is always skipped.
        self._gen_HirBlock(node.try_block)
        if node.finally_block and not self._builder.block.is_terminated:
            self._gen_HirBlock(node.finally_block)

    # ── Class / Struct ────────────────────────────────────────────────────────

    def _gen_HirClassDef(self, node: HirClassDef) -> None:
        for method in node.methods:
            if isinstance(method, HirFuncDef) and method.name:
                scoped = HirFuncDef(
                    name=f"{node.name}__{method.name}",
                    params=method.params,
                    return_type=method.return_type,
                    body=method.body,
                    is_variadic=method.is_variadic,
                )
                self._compile_func(scoped)

    def _gen_HirStructDef(self, _node: HirStructDef) -> None:
        pass  # Structs map to luz_object_t at runtime; no LLVM type needed.

    def _gen_HirImport(self, _node: HirImport) -> None:
        pass  # Imports are resolved before codegen.

    # ── Compilation ──────────────────────────────────────────────────────────

    def verify(self) -> None:
        """Verify the generated LLVM module (raises on malformed IR)."""
        mod = llvm.parse_assembly(str(self.module))
        mod.verify()

    def compile_to_object(self, output_path: str, opt: int = 2) -> None:
        """Compile the module to a native object file."""
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        target  = llvm.Target.from_default_triple()
        machine = target.create_target_machine(
            opt=opt, reloc="pic", codemodel="default"
        )
        mod = llvm.parse_assembly(str(self.module))
        mod.verify()

        obj = machine.emit_object(mod)
        with open(output_path, "wb") as f:
            f.write(obj)

    def compile_to_exe(self, output_path: str,
                       runtime_obj: str = "luz/runtime/luz_runtime.o",
                       rt_ops_obj:  str = "luz/runtime/luz_rt_ops.o") -> None:
        """Compile + link the program into a standalone executable."""
        import subprocess, os, tempfile

        fd, obj_path = tempfile.mkstemp(suffix=".o")
        os.close(fd)
        try:
            self.compile_to_object(obj_path)
            objs = [obj_path]
            for extra in (runtime_obj, rt_ops_obj):
                if os.path.exists(extra):
                    objs.append(extra)
            subprocess.run(["gcc", *objs, "-o", output_path, "-lm"],
                           check=True, stderr=subprocess.DEVNULL)
        finally:
            if os.path.exists(obj_path):
                os.remove(obj_path)
