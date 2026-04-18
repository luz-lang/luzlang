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
    HirList, HirTuple, HirDict, HirImport, HirAttemptRescue, HirAlert, HirPass,
    HirNewObj, HirObjectCall, HirIsInstance,
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
        self._is_windows = "windows" in triple

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

        # ── Class registry (populated as HirClassDef nodes are compiled) ──
        self._class_defs:    dict[str, HirClassDef]       = {}
        self._class_attrs:   dict[str, list]              = {}
        self._class_ids:     dict[str, int]               = {}
        self._class_parents: dict[str, Optional[str]]     = {}
        self._next_class_id: int                          = 1

        self._declare_runtime()
        if self._is_windows:
            self._declare_windows_abi()

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

        # Class registry / object dispatch (luz_rt_class)
        self._fn("luz_rt_register_class",  v,  self.i32, p, self.i64)
        self._fn("luz_rt_set_parent",      v,  self.i32, self.i32)
        self._fn("luz_rt_register_attr",   v,  self.i32, self.i32, p)
        self._fn("luz_rt_register_method", v,  self.i32, p, p, self.i32)
        self._fn("luz_rt_new_obj",         vt, self.i32)
        self._fn("luz_rt_obj_call",        vt, vt, p, p, self.i32)
        self._fn("luz_rt_isinstance",      vt, vt, self.i32)

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

    def _declare_windows_abi(self):
        """Declare pointer-wrapped (_pw) versions of every runtime function that
        passes or returns a luz_value_t, to avoid the Windows x64 struct ABI
        mismatch between LLVM-generated code and MinGW-compiled C.

        Wrapper signature rules:
          - If original returns val_t  → _pw returns void, first arg is ptr (out)
          - If original returns other  → _pw keeps original return type
          - Each val_t argument        → becomes ptr in _pw
          - Non-val_t arguments        → unchanged
        """
        for name, orig_fn in list(self._runtime.items()):
            ftype = orig_fn.function_type
            has_val_arg   = any(pt == self.val_t for pt in ftype.args)
            returns_val_t = ftype.return_type == self.val_t
            if not has_val_arg and not returns_val_t:
                continue  # no struct involvement — no wrapper needed

            pw_args = []
            if returns_val_t:
                pw_args.append(self.ptr)  # first arg: output pointer

            for pt in ftype.args:
                pw_args.append(self.ptr if pt == self.val_t else pt)

            pw_ret   = self.void if returns_val_t else ftype.return_type
            pw_ftype = ir.FunctionType(pw_ret, pw_args)
            pw_fn    = ir.Function(self.module, pw_ftype, name=name + "_pw")
            pw_fn.linkage = "external"
            self._runtime[name + "_pw"] = pw_fn

    def _rt_call(self, name: str, args: list) -> ir.Value:
        """Call a runtime function, routing through the pointer-wrapped version
        on Windows to avoid the struct-by-value ABI mismatch.

        Returns:
          - The luz_value_t result for value-returning functions.
          - null_val  for void functions.
          - The raw result (e.g. i1) for other return types (luz_rt_truthy).
        """
        orig_fn  = self._rt(name)
        ftype    = orig_fn.function_type
        orig_ret = ftype.return_type

        if not self._is_windows:
            result = self._builder.call(orig_fn, args)
            return result if orig_ret != self.void else self._null_val()

        pw_fn = self._runtime.get(name + "_pw")
        if pw_fn is None:
            # No wrapper exists (function has no val_t involvement).
            result = self._builder.call(orig_fn, args)
            return result if orig_ret != self.void else self._null_val()

        returns_val_t = (orig_ret == self.val_t)
        call_args: list = []
        out_slot  = None

        if returns_val_t:
            out_slot = self._builder.alloca(self.val_t, name="pw_ret")
            call_args.append(self._builder.bitcast(out_slot, self.ptr))

        for arg, pt in zip(args, ftype.args):
            if pt == self.val_t:
                slot = self._builder.alloca(self.val_t)
                self._builder.store(arg, slot)
                call_args.append(self._builder.bitcast(slot, self.ptr))
            else:
                call_args.append(arg)

        result = self._builder.call(pw_fn, call_args)

        if returns_val_t:
            return self._builder.load(out_slot, name="pw_result")
        if orig_ret == self.void:
            return self._null_val()
        return result  # e.g. i1 for luz_rt_truthy

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
            return self._rt_call("luz_rt_str_literal", [data_ptr, length])
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
            return self._rt_call(rt, [left, right])
        return self._null_val()

    def _gen_HirUnaryOp(self, node: HirUnaryOp) -> ir.Value:
        operand = self.gen(node.operand)
        if node.op == "-":
            return self._rt_call("luz_rt_neg", [operand])
        if node.op == "not":
            return self._rt_call("luz_rt_not", [operand])
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
        cond_i1  = self._rt_call("luz_rt_truthy", [cond_val])

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
        cond_i1  = self._rt_call("luz_rt_truthy", [cond_val])
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
        is_main = (self._func.function_type.return_type == self.i32)

        # Multi-return: `return a, b` — emit a stack-allocated struct { val_t x N }.
        if not is_main and isinstance(node.value, HirTuple):
            struct_val = self._gen_HirTuple(node.value)
            self._builder.ret(struct_val)
            return

        # Emit a tail call when returning the result of a user-function call
        # in a non-main function.  This lets LLVM's TCO pass eliminate the frame.
        if not is_main and node.value is not None and isinstance(node.value, HirCall):
            val = self._gen_tail_call(node.value)
            if val is not None:
                self._builder.ret(val)
                return

        val = self.gen(node.value) if node.value is not None else self._null_val()
        if is_main:
            # Extract the integer data field as the exit code
            data = self._builder.extract_value(val, 2)
            code = self._builder.trunc(data, self.i32)
            self._builder.ret(code)
        else:
            self._builder.ret(val)

    def _gen_tail_call(self, node: HirCall) -> Optional[ir.Value]:
        """Emit a HirCall in tail position with the musttail / tail attribute.

        Returns the call ir.Value so the caller can emit ``ret`` immediately
        after, or None if the call was not to a user-defined function (runtime
        calls are emitted normally via _rt_call and returned as-is).
        """
        args = [self.gen(a) for a in node.args]

        if node.func in self._user_funcs:
            fn          = self._user_funcs[node.func]
            param_count = len(fn.function_type.args)
            padded      = list(args)
            while len(padded) < param_count:
                padded.append(self._null_val())
            call = self._builder.call(fn, padded[:param_count])
            # musttail: LLVM *must* eliminate the call frame.  Valid only when
            # callee signature == caller signature (guaranteed for self-recursion
            # since all Luz functions return val_t and take val_t args).
            # For calls to other user functions we use `tail` as a hint.
            call.tail = 'musttail' if fn is self._func else 'tail'
            return call

        # Runtime call — fall through to normal generation so _rt_call handles
        # the Windows ABI wrappers correctly.
        rt_name = self._BUILTIN_RT.get(node.func)
        if rt_name and rt_name in self._runtime:
            return self._rt_call(rt_name, args)

        return None

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

    def _tuple_ret_type(self, arity: int) -> ir.LiteralStructType:
        """Return the LLVM struct type used for a multi-return of *arity* values."""
        return ir.LiteralStructType([self.val_t] * arity)

    def _get_multi_return_arity(self, body: 'HirBlock') -> int:
        """Walk body to find the first HirReturn(HirTuple) and return its arity."""
        for stmt in body.stmts:
            if isinstance(stmt, HirReturn) and isinstance(stmt.value, HirTuple):
                return len(stmt.value.elements)
            if isinstance(stmt, HirIf):
                n = self._get_multi_return_arity(stmt.then_block)
                if n > 0:
                    return n
                if stmt.else_block:
                    n = self._get_multi_return_arity(stmt.else_block)
                    if n > 0:
                        return n
            if isinstance(stmt, HirWhile):
                n = self._get_multi_return_arity(stmt.block)
                if n > 0:
                    return n
            if isinstance(stmt, HirBlock):
                n = self._get_multi_return_arity(stmt)
                if n > 0:
                    return n
        return 0

    def _compile_func(self, node: HirFuncDef) -> ir.Function:
        param_types = [self.val_t] * len(node.params)
        if node.is_multi_return:
            arity    = self._get_multi_return_arity(node.body)
            ret_type = self._tuple_ret_type(arity) if arity > 0 else self.val_t
        else:
            ret_type = self.val_t
        ftype = ir.FunctionType(ret_type, param_types)
        name  = node.name or self.module.get_unique_name("lambda")
        fn    = ir.Function(self.module, ftype, name=name)
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

        # Store a luz_value_t{TAG_FUNCTION, 0, fn_ptr} in the outer scope so
        # that HirLoad(name) returns a callable function value.  This enables
        # functions assigned to variables and passed as arguments.
        if node.name and self._scope_stack:
            fn_as_ptr = self._builder.bitcast(fn, self.ptr)
            fn_i64    = self._builder.ptrtoint(fn_as_ptr, self.i64)
            func_val  = self._build_val(ir.Constant(self.i32, self.TAG_FUNCTION), fn_i64)
            slot      = self._alloca(node.name)
            self._builder.store(func_val, slot)
            self._define(node.name, slot)

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

        # Class constructor: Foo(x, y) → create object + call Foo__init
        if node.func in self._class_ids:
            return self._gen_class_new(node.func, args)

        rt_name = self._BUILTIN_RT.get(node.func)
        if rt_name and rt_name in self._runtime:
            return self._rt_call(rt_name, args)

        if node.func in self._user_funcs:
            return self._builder.call(self._user_funcs[node.func], args)

        return self._null_val()

    def _gen_HirExprCall(self, node: HirExprCall) -> ir.Value:
        args = [self.gen(a) for a in node.args]

        # Fast path: if the callee is a load of a name we already compiled,
        # call it directly (avoids the ptrtoi/inttoptr round-trip).
        if isinstance(node.callee, HirLoad) and node.callee.name in self._user_funcs:
            fn          = self._user_funcs[node.callee.name]
            param_count = len(fn.function_type.args)
            padded      = list(args)
            while len(padded) < param_count:
                padded.append(self._null_val())
            return self._builder.call(fn, padded[:param_count])

        # General indirect call: callee is an arbitrary expression that
        # evaluates to a luz_value_t with TAG_FUNCTION.  Extract the function
        # pointer from the 64-bit data field and call it indirectly.
        callee_val = self.gen(node.callee)
        fn_i64     = self._builder.extract_value(callee_val, 2)
        ftype      = ir.FunctionType(self.val_t, [self.val_t] * len(args))
        fn_ptr     = self._builder.inttoptr(fn_i64, ir.PointerType(ftype))
        return self._builder.call(fn_ptr, args)

    # ── Collections ───────────────────────────────────────────────────────────

    def _gen_HirList(self, node: HirList) -> ir.Value:
        n   = ir.Constant(self.i32, len(node.elements))
        lst = self._rt_call("luz_rt_make_list", [n])
        for elem in node.elements:
            val = self.gen(elem)
            self._rt_call("luz_builtin_append", [lst, val])
        return lst

    def _gen_HirTuple(self, node: HirTuple) -> ir.Value:
        """Emit a stack-allocated LLVM struct { val_t x N } for multi-return.

        In return position this struct is returned in registers (LLVM handles
        small structs automatically).  No heap allocation occurs.
        """
        n        = len(node.elements)
        struct_t = self._tuple_ret_type(n)
        result   = ir.Constant(struct_t, ir.Undefined)
        for i, elem in enumerate(node.elements):
            val    = self.gen(elem)
            result = self._builder.insert_value(result, val, i)
        return result

    def _gen_HirDict(self, node: HirDict) -> ir.Value:
        n = ir.Constant(self.i32, len(node.pairs))
        d = self._rt_call("luz_rt_make_dict", [n])
        for k_node, v_node in node.pairs:
            k = self.gen(k_node)
            v = self.gen(v_node)
            self._rt_call("luz_rt_setindex", [d, k, v])
        return d

    # ── Field / index access ──────────────────────────────────────────────────

    def _gen_HirFieldLoad(self, node: HirFieldLoad) -> ir.Value:
        obj  = self.gen(node.obj)
        name = self._cstr(node.field)
        return self._rt_call("luz_rt_getfield", [obj, name])

    def _gen_HirFieldStore(self, node: HirFieldStore) -> None:
        obj   = self.gen(node.obj)
        name  = self._cstr(node.field)
        value = self.gen(node.value)
        self._rt_call("luz_rt_setfield", [obj, name, value])

    def _gen_HirIndex(self, node: HirIndex) -> ir.Value:
        coll  = self.gen(node.collection)
        index = self.gen(node.index)
        return self._rt_call("luz_rt_getindex", [coll, index])

    def _gen_HirIndexStore(self, node: HirIndexStore) -> None:
        coll  = self.gen(node.collection)
        index = self.gen(node.index)
        value = self.gen(node.value)
        self._rt_call("luz_rt_setindex", [coll, index, value])

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
        self._rt_call("luz_raise", [val])
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
        name     = node.name
        class_id = self._next_class_id
        self._next_class_id += 1

        self._class_defs[name]    = node
        self._class_ids[name]     = class_id
        self._class_parents[name] = node.parent

        # Collect attribute names (parent attrs first, then own attrs from init).
        attrs = self._collect_class_attrs(node)
        self._class_attrs[name] = attrs

        # ── Emit runtime registration calls ───────────────────────────────
        parent_id = (self._class_ids.get(node.parent, 0)
                     if node.parent else 0)

        self._rt_call("luz_rt_register_class", [
            ir.Constant(self.i32, class_id),
            self._cstr(name),
            ir.Constant(self.i64, len(attrs)),
        ])
        self._rt_call("luz_rt_set_parent", [
            ir.Constant(self.i32, class_id),
            ir.Constant(self.i32, parent_id),
        ])
        for slot, attr in enumerate(attrs):
            self._rt_call("luz_rt_register_attr", [
                ir.Constant(self.i32, class_id),
                ir.Constant(self.i32, slot),
                self._cstr(attr),
            ])

        # ── Compile methods with name-mangling and register them ──────────
        for method in node.methods:
            if not (isinstance(method, HirFuncDef) and method.name):
                continue
            mangled = f"{name}__{method.name}"
            scoped  = HirFuncDef(
                name=mangled,
                params=method.params,
                return_type=method.return_type,
                body=method.body,
                is_variadic=method.is_variadic,
                is_multi_return=method.is_multi_return,
            )
            fn      = self._compile_func(scoped)
            cb_fn   = self._gen_method_cb(fn, len(method.params))
            cb_ptr  = self._builder.bitcast(cb_fn, self.ptr)
            nparams = ir.Constant(self.i32, len(method.params))
            self._rt_call("luz_rt_register_method", [
                ir.Constant(self.i32, class_id),
                self._cstr(method.name),   # unmangled — used for dispatch
                cb_ptr,
                nparams,
            ])

    def _gen_method_cb(self, fn: ir.Function, nparams: int) -> ir.Function:
        """Wrap a method function in a pointer-only callback so GCC-compiled
        dispatch code can call it without struct-by-value ABI ambiguity.

        Signature: void cb(i8* out, i8* arg0, i8* arg1, ..., i8* argN)
          - out   : pointer where the luz_value_t result is written
          - arg0..N: pointers to the luz_value_t arguments (self is arg0)
        """
        ptr_t   = self.ptr
        pw_type = ir.FunctionType(self.void, [ptr_t] * (1 + nparams))
        pw_fn   = ir.Function(self.module, pw_type, name=fn.name + "__cb")

        entry = pw_fn.append_basic_block("entry")
        saved = (self._builder, self._func, self._scope_stack,
                 self._break_bb, self._continue_bb)
        self._func         = pw_fn
        self._builder      = ir.IRBuilder(entry)
        self._scope_stack  = [{}]
        self._break_bb     = None
        self._continue_bb  = None

        val_ptr_t = ir.PointerType(self.val_t)
        out_slot  = self._builder.bitcast(pw_fn.args[0], val_ptr_t, name="out")
        call_args = []
        for i, arg_ptr in enumerate(list(pw_fn.args)[1:]):
            slot = self._builder.bitcast(arg_ptr, val_ptr_t, name=f"a{i}")
            call_args.append(self._builder.load(slot, name=f"v{i}"))

        result = self._builder.call(fn, call_args)
        self._builder.store(result, out_slot)
        self._builder.ret_void()

        (self._builder, self._func, self._scope_stack,
         self._break_bb, self._continue_bb) = saved
        return pw_fn

    # ── Class helpers ─────────────────────────────────────────────────────────

    def _collect_class_attrs(self, node: HirClassDef) -> list:
        """Return ordered list of attribute names for this class.

        Parent attributes come first (in the parent's order), followed by
        attributes introduced in this class's init method body.
        """
        attrs: list = []
        seen:  set  = set()

        # Inherit parent attributes first.
        if node.parent and node.parent in self._class_attrs:
            for a in self._class_attrs[node.parent]:
                if a not in seen:
                    attrs.append(a)
                    seen.add(a)

        # Scan init method body for  self.xxx = ...  patterns.
        for m in node.methods:
            if isinstance(m, HirFuncDef) and m.name == "init":
                self._scan_attrs(m.body, attrs, seen)
                break

        return attrs

    def _scan_attrs(self, block: HirBlock, attrs: list, seen: set) -> None:
        """Recursively scan *block* for HirFieldStore on self."""
        for stmt in block.stmts:
            if (isinstance(stmt, HirFieldStore)
                    and isinstance(stmt.obj, HirLoad)
                    and stmt.obj.name == "self"
                    and stmt.field not in seen):
                attrs.append(stmt.field)
                seen.add(stmt.field)
            elif isinstance(stmt, HirBlock):
                self._scan_attrs(stmt, attrs, seen)
            elif isinstance(stmt, HirIf):
                self._scan_attrs(stmt.then_block, attrs, seen)
                if stmt.else_block:
                    self._scan_attrs(stmt.else_block, attrs, seen)
            elif isinstance(stmt, HirWhile):
                self._scan_attrs(stmt.block, attrs, seen)

    def _gen_class_new(self, class_name: str, init_args: list) -> ir.Value:
        """Emit code for ClassName(args...).

        1. Call luz_rt_new_obj(class_id) → allocates the object.
        2. If an init method was compiled, call it with (obj, *init_args).
        3. Return the new object value.
        """
        class_id = self._class_ids[class_name]
        obj = self._rt_call("luz_rt_new_obj",
                            [ir.Constant(self.i32, class_id)])

        init_fn_name = f"{class_name}__init"
        if init_fn_name in self._user_funcs:
            fn          = self._user_funcs[init_fn_name]
            param_count = len(fn.function_type.args)
            all_args    = [obj] + list(init_args)
            padded      = all_args[:param_count]
            while len(padded) < param_count:
                padded.append(self._null_val())
            self._builder.call(fn, padded)

        return obj

    def _gen_HirObjectCall(self, node: HirObjectCall) -> ir.Value:
        """Emit a runtime-dispatched method call: obj.method(args...)."""
        obj     = self.gen(node.obj)
        args_ir = [self.gen(a) for a in node.args]
        n       = len(args_ir)

        if n == 0:
            arr_ptr = ir.Constant(self.ptr, None)
        else:
            arr_t = ir.ArrayType(self.val_t, n)
            arr   = self._builder.alloca(arr_t, name="margs")
            zero  = ir.Constant(self.i32, 0)
            for i, arg in enumerate(args_ir):
                slot = self._builder.gep(arr,
                           [zero, ir.Constant(self.i32, i)],
                           inbounds=True)
                self._builder.store(arg, slot)
            arr_ptr = self._builder.bitcast(arr, self.ptr)

        method_ptr = self._cstr(node.method)
        nargs      = ir.Constant(self.i32, n)
        return self._rt_call("luz_rt_obj_call",
                             [obj, method_ptr, arr_ptr, nargs])

    def _gen_HirIsInstance(self, node: HirIsInstance) -> ir.Value:
        """Emit isinstance(obj, ClassName) check."""
        obj      = self.gen(node.obj)
        class_id = self._class_ids.get(node.class_name, 0)
        return self._rt_call("luz_rt_isinstance",
                             [obj, ir.Constant(self.i32, class_id)])

    def _gen_HirStructDef(self, _node: HirStructDef) -> None:
        pass  # Structs map to luz_object_t at runtime; no LLVM type needed.

    def _gen_HirImport(self, _node: HirImport) -> None:
        pass  # Imports are resolved before codegen.

    # ── Compilation ──────────────────────────────────────────────────────────

    def verify(self) -> None:
        """Verify the generated LLVM module (raises on malformed IR)."""
        mod = llvm.parse_assembly(str(self.module))
        mod.verify()

    def _run_passes(self, mod, machine, opt: int) -> None:
        """Run the LLVM middle-end optimization pipeline on a parsed module.

        create_target_machine(opt=N) only controls the backend (register
        allocation, instruction scheduling).  The middle-end passes — SROA,
        inlining, constant propagation, dead code elimination, loop
        optimizations — require an explicit pass pipeline run.

        Key wins for Luz specifically:
          - SROA/mem2reg promotes the alloca/store/load triples emitted by
            the _pw Windows ABI wrappers to SSA values, removing the overhead.
          - Inlining folds trivial runtime helpers into callers.
          - Constant propagation folds expressions that hir.py didn't fold.
          - DCE removes unreachable code blocks.
        """
        pto = llvm.newpassmanagers.PipelineTuningOptions(speed_level=opt)
        pb  = llvm.create_pass_builder(machine, pto)
        pm  = pb.getModulePassManager()

        # Core passes that have the most impact for generated Luz code.
        pm.add_sroa_pass()                   # promote allocas → SSA registers
        pm.add_instruction_combine_pass()    # peephole + algebraic simplification
        pm.add_simplify_cfg_pass()           # remove unreachable / merge blocks
        pm.add_dead_store_elimination_pass() # remove stores whose value is unused
        pm.add_aggressive_dce_pass()         # remove dead instructions
        pm.add_constant_merge_pass()         # deduplicate constant globals
        pm.add_global_opt_pass()             # optimise global variables
        if opt >= 2:
            pm.add_tail_call_elimination_pass()
            pm.add_jump_threading_pass()
            pm.add_mem_copy_opt_pass()       # replace memcpy patterns

        pm.run(mod, pb)

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
        if opt > 0:
            self._run_passes(mod, machine, opt)

        obj = machine.emit_object(mod)
        with open(output_path, "wb") as f:
            f.write(obj)

    def compile_to_exe(self, output_path: str,
                       runtime_obj:    str = "luz/runtime/luz_runtime.o",
                       rt_ops_obj:     str = "luz/runtime/luz_rt_ops.o",
                       rt_class_obj:   str = "luz/runtime/luz_rt_class.o",
                       rt_win_abi_obj: str = "luz/runtime/luz_rt_win_abi.o") -> None:
        """Compile + link the program into a standalone executable."""
        import subprocess, os, sys, tempfile

        fd, obj_path = tempfile.mkstemp(suffix=".o")
        os.close(fd)
        try:
            self.compile_to_object(obj_path)
            objs = [obj_path]
            for extra in (runtime_obj, rt_ops_obj, rt_class_obj, rt_win_abi_obj):
                if os.path.exists(extra):
                    objs.append(extra)

            # On Windows, the system gcc may be a 32-bit MinGW that cannot link
            # the 64-bit COFF objects produced by llvmlite.  Prefer the MSYS2
            # MinGW64 toolchain which is the same environment used to build the
            # runtime.
            gcc = "gcc"
            if sys.platform == "win32":
                msys2_gcc = r"C:\msys64\mingw64\bin\gcc.exe"
                if os.path.exists(msys2_gcc):
                    gcc = msys2_gcc

            subprocess.run([gcc, *objs, "-o", output_path, "-lm"],
                           check=True, stderr=subprocess.DEVNULL)
        finally:
            if os.path.exists(obj_path):
                os.remove(obj_path)
