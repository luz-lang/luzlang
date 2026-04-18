# hir.py — High-level Intermediate Representation for the Luz compiler.
#
# HIR sits between the AST (produced by the parser) and LLVM IR.
# Its two responsibilities are:
#   1. Make every type explicit (every node carries a `type` annotation).
#   2. Desugar complex language constructs into a minimal, flat set of
#      primitives that map directly to LLVM IR patterns.
#
# Usage:
#   from luz.hir import Lowering
#   hir_program = Lowering().lower_program(ast)   # list[HirNode]
#
# Desugaring performed by the Lowering pass:
#   for i = s to e step k  →  while loop with explicit counter
#   for x in list           →  index-based while loop
#   switch/case             →  if/elif/else chain
#   match expr { }          →  chain of equality checks
#   x ?? y                  →  if x != null { x } else { y }
#   a if cond else b        →  if cond { a } else { b }
#   f"hello {x}"            →  series of string concatenations via to_str()
#   dot method calls        →  top-level runtime function calls

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Optional

# ── HIR type strings (mirrors the typechecker's T constants) ─────────────────

HIR_UNKNOWN  = "unknown"
HIR_NULL     = "null"
HIR_BOOL     = "bool"
HIR_INT      = "int"
HIR_FLOAT    = "float"
HIR_STRING   = "string"
HIR_LIST     = "list"
HIR_DICT     = "dict"
HIR_FUNCTION = "function"

def _hir_type_of(v) -> str:
    """Return the HIR type constant for a Python literal value."""
    if isinstance(v, bool):   return HIR_BOOL
    if isinstance(v, int):    return HIR_INT
    if isinstance(v, float):  return HIR_FLOAT
    if isinstance(v, str):    return HIR_STRING
    if v is None:             return HIR_NULL
    return HIR_UNKNOWN


# ── HIR node definitions ─────────────────────────────────────────────────────

@dataclass
class HirLiteral:
    """A compile-time constant value."""
    value: Any          # Python int, float, str, bool, or None
    type: str = HIR_UNKNOWN


@dataclass
class HirLoad:
    """Read a named variable from the current scope."""
    name: str
    type: str = HIR_UNKNOWN


@dataclass
class HirLet:
    """Introduce a new local variable (first assignment in a scope)."""
    name: str
    type: str
    value: Any   # HirNode


@dataclass
class HirAssign:
    """Reassign an existing variable."""
    name: str
    value: Any   # HirNode


@dataclass
class HirBinOp:
    """Binary operation with explicit result type."""
    op: str      # "+", "-", "*", "/", "//", "%", "**", "==", "!=",
                 # "<", "<=", ">", ">=", "and", "or", "in", "not in"
    left: Any    # HirNode
    right: Any   # HirNode
    type: str = HIR_UNKNOWN


@dataclass
class HirUnaryOp:
    """Unary operation."""
    op: str      # "-", "not"
    operand: Any # HirNode
    type: str = HIR_UNKNOWN


@dataclass
class HirCall:
    """Call a named function."""
    func: str
    args: list
    kwargs: dict = dc_field(default_factory=dict)
    return_type: str = HIR_UNKNOWN


@dataclass
class HirExprCall:
    """Call an arbitrary expression (e.g. a lambda stored in a variable)."""
    callee: Any  # HirNode
    args: list
    kwargs: dict = dc_field(default_factory=dict)
    return_type: str = HIR_UNKNOWN


@dataclass
class HirBlock:
    """A sequence of statements."""
    stmts: list  # list[HirNode]


@dataclass
class HirIf:
    """Desugared if/elif/else — always binary (then / optional else)."""
    cond: Any           # HirNode
    then_block: HirBlock
    else_block: Optional[HirBlock] = None


@dataclass
class HirWhile:
    """While loop (for/foreach are desugared into this)."""
    cond: Any       # HirNode
    block: HirBlock


@dataclass
class HirReturn:
    """Return from a function."""
    value: Optional[Any] = None  # HirNode or None


@dataclass
class HirBreak:
    pass


@dataclass
class HirContinue:
    pass


@dataclass
class HirFieldLoad:
    """Load an attribute from an object: obj.field"""
    obj: Any    # HirNode
    field: str
    type: str = HIR_UNKNOWN


@dataclass
class HirFieldStore:
    """Store an attribute on an object: obj.field = value"""
    obj: Any    # HirNode
    field: str
    value: Any  # HirNode


@dataclass
class HirIndex:
    """Index into a collection: collection[index]"""
    collection: Any  # HirNode
    index: Any       # HirNode
    type: str = HIR_UNKNOWN


@dataclass
class HirIndexStore:
    """Store into a collection: collection[index] = value"""
    collection: Any  # HirNode
    index: Any       # HirNode
    value: Any       # HirNode


@dataclass
class HirList:
    """List literal: [e0, e1, …]"""
    elements: list  # list[HirNode]
    type: str = HIR_LIST


@dataclass
class HirTuple:
    """Multi-return tuple literal: (e0, e1, …).

    Distinct from HirList: the interpreter treats this like a list, but the
    compiler emits a stack-allocated LLVM struct { val_t x N } — no heap
    allocation.  Used exclusively for `return a, b` and destructure RHS.
    """
    elements: list  # list[HirNode]
    type: str = HIR_LIST


@dataclass
class HirDict:
    """Dict literal: {k0: v0, k1: v1, …}"""
    pairs: list  # list[(HirNode, HirNode)]
    type: str = HIR_DICT


@dataclass
class HirFuncDef:
    """Function definition."""
    name: Optional[str]           # None for anonymous functions
    params: list                  # [(name: str, type: str), …]
    return_type: str
    body: HirBlock
    is_variadic: bool = False
    is_multi_return: bool = False  # True if any return yields a HirTuple


@dataclass
class HirClassDef:
    """Class definition."""
    name: str
    parent: Optional[str]
    methods: list  # list[HirFuncDef]


@dataclass
class HirStructDef:
    """Struct definition."""
    name: str
    fields: list   # [(name: str, type: str, default: HirNode|None), …]


@dataclass
class HirImport:
    """Import statement."""
    path: str
    alias: Optional[str]
    names: list  # list[str] — for 'from x import a, b'


@dataclass
class HirAttemptRescue:
    """attempt / rescue / finally block."""
    try_block: HirBlock
    error_var: Optional[str]
    rescue_block: HirBlock
    finally_block: Optional[HirBlock]


@dataclass
class HirAlert:
    """alert(expr) — raises a user-level exception."""
    value: Any  # HirNode


@dataclass
class HirPass:
    """No-op placeholder."""
    pass


@dataclass
class HirNewObj:
    """Instantiate a class: ClassName(args...).
    args does NOT include self — the codegen creates the object first."""
    class_name: str
    args: list       # list[HirNode]
    type: str = HIR_UNKNOWN


@dataclass
class HirObjectCall:
    """Call a user-defined method on an object: obj.method(args...).
    args does NOT include self — obj IS self."""
    obj: Any         # HirNode
    method: str      # unmangled method name (e.g. "get", "init")
    args: list       # list[HirNode]
    type: str = HIR_UNKNOWN


@dataclass
class HirIsInstance:
    """isinstance(obj, ClassName) — checked via the class registry."""
    obj: Any         # HirNode
    class_name: str


# ── Lowering pass ─────────────────────────────────────────────────────────────

class Lowering:
    """
    Lowers Luz AST nodes to HIR nodes.

    Usage:
        from luz.hir import Lowering
        hir = Lowering().lower_program(ast_list)
    """

    def __init__(self):
        self._temp_counter = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def lower_program(self, ast: list) -> list:
        """Lower an entire top-level AST to a flat list of HIR nodes."""
        result = []
        for node in ast:
            lowered = self.lower(node)
            if isinstance(lowered, HirBlock):
                result.extend(lowered.stmts)
            elif lowered is not None:
                result.append(lowered)
        return result

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def lower(self, node) -> Any:
        if node is None:
            return HirLiteral(None, HIR_NULL)
        method = f"lower_{type(node).__name__}"
        return getattr(self, method, self._lower_unknown)(node)

    def _lower_unknown(self, node) -> Any:
        # Graceful fallback: emit a null literal so the pass never crashes.
        return HirLiteral(None, HIR_NULL)

    def _fresh(self, prefix: str = "__t") -> str:
        n = self._temp_counter
        self._temp_counter += 1
        return f"{prefix}{n}"

    def _block(self, stmts: list) -> HirBlock:
        result = []
        for s in stmts:
            lowered = self.lower(s)
            if isinstance(lowered, HirBlock):
                result.extend(lowered.stmts)
            elif lowered is not None:
                result.append(lowered)
        return HirBlock(result)

    def _analyze_multi_return(self, block: HirBlock) -> bool:
        """Return True if any HirReturn in block (recursively) yields a HirTuple."""
        for stmt in block.stmts:
            if isinstance(stmt, HirReturn) and isinstance(stmt.value, HirTuple):
                return True
            if isinstance(stmt, HirIf):
                if self._analyze_multi_return(stmt.then_block):
                    return True
                if stmt.else_block and self._analyze_multi_return(stmt.else_block):
                    return True
            if isinstance(stmt, HirWhile):
                if self._analyze_multi_return(stmt.block):
                    return True
            if isinstance(stmt, HirBlock):
                if self._analyze_multi_return(stmt):
                    return True
        return False

    # ── Literals ──────────────────────────────────────────────────────────────

    def lower_NumberNode(self, node) -> HirLiteral:
        from luz.lexer import TokenType
        if node.token.type == TokenType.INT:
            return HirLiteral(int(node.token.value), HIR_INT)
        return HirLiteral(float(node.token.value), HIR_FLOAT)

    def lower_StringNode(self, node) -> HirLiteral:
        return HirLiteral(node.token.value, HIR_STRING)

    def lower_BooleanNode(self, node) -> HirLiteral:
        return HirLiteral(node.token.value == "true", HIR_BOOL)

    def lower_NullNode(self, _) -> HirLiteral:
        return HirLiteral(None, HIR_NULL)

    def lower_ListNode(self, node) -> HirList:
        return HirList([self.lower(e) for e in node.elements])

    def lower_DictNode(self, node) -> HirDict:
        return HirDict([(self.lower(k), self.lower(v)) for k, v in node.pairs])

    def lower_TupleNode(self, node) -> HirTuple:
        # Tuples use HirTuple so the compiler can emit a stack-allocated struct.
        # The interpreter treats HirTuple the same as HirList at runtime.
        return HirTuple([self.lower(e) for e in node.elements])

    # ── Format strings → concat chain ─────────────────────────────────────────

    def lower_FStringNode(self, node) -> Any:
        """Desugar $"hello {x} world" into a chain of string concatenations."""
        parts = []
        for part in node.parts:
            if isinstance(part, str):
                if part:  # skip empty string segments
                    parts.append(HirLiteral(part, HIR_STRING))
            else:
                # Embedded expression — wrap in to_str()
                expr = self.lower(part)
                parts.append(HirCall("to_str", [expr], return_type=HIR_STRING))

        if not parts:
            return HirLiteral("", HIR_STRING)
        acc = parts[0]
        for p in parts[1:]:
            acc = HirBinOp("+", acc, p, HIR_STRING)
        return acc

    # ── Variables ─────────────────────────────────────────────────────────────

    def lower_VarAccessNode(self, node) -> HirLoad:
        return HirLoad(node.token.value)

    def lower_VarAssignNode(self, node) -> Any:
        name = node.var_name_token.value
        value = self.lower(node.value_node)
        return HirAssign(name, value)

    def lower_TypedVarAssignNode(self, node) -> HirLet:
        return HirLet(
            name=node.var_token.value,
            type=node.type_name or HIR_UNKNOWN,
            value=self.lower(node.value_node),
        )

    def lower_ConstDefNode(self, node) -> HirLet:
        return HirLet(
            name=node.var_token.value,
            type=node.type_name or HIR_UNKNOWN,
            value=self.lower(node.value_node),
        )

    def lower_DestructureAssignNode(self, node) -> HirBlock:
        rhs = self.lower(node.value_node)
        if isinstance(rhs, HirTuple) and len(rhs.elements) == len(node.var_tokens):
            # Static tuple: unpack elements directly — no runtime list allocation.
            return HirBlock([
                HirAssign(tok.value, rhs.elements[i])
                for i, tok in enumerate(node.var_tokens)
            ])
        # Dynamic value: use runtime list indexing.
        # [a, b, c] = expr  →  tmp = expr; a = tmp[0]; b = tmp[1]; c = tmp[2]
        tmp = self._fresh("__dest")
        stmts = [HirLet(tmp, HIR_LIST, rhs)]
        for i, tok in enumerate(node.var_tokens):
            stmts.append(HirAssign(
                tok.value,
                HirIndex(HirLoad(tmp), HirLiteral(i, HIR_INT))
            ))
        return HirBlock(stmts)

    def lower_DictDestructureAssignNode(self, node) -> HirBlock:
        # {a, b} = expr  →  tmp = expr; a = tmp["a"]; b = tmp["b"]
        tmp = self._fresh("__ddest")
        stmts = [HirLet(tmp, HIR_DICT, self.lower(node.value_node))]
        for tok in node.key_tokens:
            stmts.append(HirAssign(
                tok.value,
                HirIndex(HirLoad(tmp), HirLiteral(tok.value, HIR_STRING))
            ))
        return HirBlock(stmts)

    # ── Operators ─────────────────────────────────────────────────────────────

    # Map TokenType → operator string used by codegen's _BINOP_RT table.
    _BINOP_TOKEN_OP = {
        "PLUS":    "+",
        "MINUS":   "-",
        "MUL":     "*",
        "DIV":     "/",
        "IDIV":    "//",
        "MOD":     "%",
        "POW":     "**",
        "EE":      "==",
        "NE":      "!=",
        "LT":      "<",
        "LTE":     "<=",
        "GT":      ">",
        "GTE":     ">=",
        "AND":     "and",
        "OR":      "or",
        "IN":      "in",
        "NOT_IN":  "not in",
    }

    def lower_BinOpNode(self, node) -> "HirBinOp | HirLiteral":
        tok_name = node.op_token.type.name
        op   = self._BINOP_TOKEN_OP.get(tok_name, node.op_token.value)
        left = self.lower(node.left_node)
        right = self.lower(node.right_node)

        # Constant folding: evaluate at compile time when both sides are literals.
        if isinstance(left, HirLiteral) and isinstance(right, HirLiteral):
            folded = self._fold_bin(op, left.value, right.value)
            if folded is not None:
                return HirLiteral(folded, _hir_type_of(folded))

        return HirBinOp(op=op, left=left, right=right)

    @staticmethod
    def _fold_bin(op: str, lv, rv):
        """Evaluate a binary op on two literal Python values.
        Returns the folded result, or None if folding is not safe/applicable."""
        # Skip bool operands for arithmetic — Luz booleans are not integers.
        is_num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        try:
            if op == "+":
                if is_num(lv) and is_num(rv):   return lv + rv
                if isinstance(lv, str) and isinstance(rv, str): return lv + rv
            elif op == "-":
                if is_num(lv) and is_num(rv):   return lv - rv
            elif op == "*":
                if is_num(lv) and is_num(rv):   return lv * rv
                if isinstance(lv, str) and isinstance(rv, int) and not isinstance(rv, bool):
                    return lv * rv
            elif op == "/":
                if is_num(lv) and is_num(rv) and rv != 0:
                    return lv / rv
            elif op == "//":
                if is_num(lv) and is_num(rv) and rv != 0:
                    import math
                    if isinstance(lv, int) and isinstance(rv, int):
                        q = lv // rv
                        return q
                    return float(math.floor(lv / rv))
            elif op == "%":
                if is_num(lv) and is_num(rv) and rv != 0:
                    return lv % rv
            elif op == "**":
                if is_num(lv) and is_num(rv):   return lv ** rv
            elif op == "==":  return lv == rv
            elif op == "!=":  return lv != rv
            elif op == "<":
                if (is_num(lv) and is_num(rv)) or (isinstance(lv, str) and isinstance(rv, str)):
                    return lv < rv
            elif op == "<=":
                if (is_num(lv) and is_num(rv)) or (isinstance(lv, str) and isinstance(rv, str)):
                    return lv <= rv
            elif op == ">":
                if (is_num(lv) and is_num(rv)) or (isinstance(lv, str) and isinstance(rv, str)):
                    return lv > rv
            elif op == ">=":
                if (is_num(lv) and is_num(rv)) or (isinstance(lv, str) and isinstance(rv, str)):
                    return lv >= rv
            elif op == "and": return lv if not lv else rv
            elif op == "or":  return lv if lv else rv
        except (TypeError, ValueError, OverflowError):
            pass
        return None

    def lower_UnaryOpNode(self, node) -> "HirUnaryOp | HirLiteral":
        op      = node.op_token.type.name
        operand = self.lower(node.node)

        # Constant fold unary minus and logical not on literals.
        if isinstance(operand, HirLiteral):
            v = operand.value
            if op == "MINUS" and isinstance(v, (int, float)) and not isinstance(v, bool):
                return HirLiteral(-v, _hir_type_of(-v))
            if op == "NOT":
                result = not bool(v)
                return HirLiteral(result, HIR_BOOL)

        # Map token type name to operator string for HirUnaryOp.
        op_str = {
            "MINUS": "-",
            "NOT":   "not",
        }.get(op, node.op_token.value)
        return HirUnaryOp(op=op_str, operand=operand)

    # ── Control flow ──────────────────────────────────────────────────────────

    def lower_IfNode(self, node) -> HirIf:
        """Lower if/elif/else into nested HirIf nodes (binary structure)."""
        # Build from the last case backwards to create nested if/else
        else_block: Optional[HirBlock] = None
        if node.else_case:
            else_block = self._block(node.else_case)

        # Process cases in reverse to nest elif as else branches
        for condition, body in reversed(node.cases):
            cond = self.lower(condition)
            then = self._block(body)
            else_block = HirBlock([HirIf(cond, then, else_block)])

        # Unwrap the outer block wrapper
        if else_block and len(else_block.stmts) == 1:
            return else_block.stmts[0]
        return HirIf(HirLiteral(False, HIR_BOOL), HirBlock([]), else_block)

    def lower_WhileNode(self, node) -> HirWhile:
        return HirWhile(
            cond=self.lower(node.condition_node),
            block=self._block(node.block),
        )

    def lower_ForNode(self, node) -> HirBlock:
        """Desugar: for i = start to end step k → while loop with counter."""
        var   = node.var_name_token.value
        start = self.lower(node.start_value_node)
        end   = self.lower(node.end_value_node)
        step  = self.lower(node.step_node) if node.step_node else HirLiteral(1, HIR_INT)

        tmp_end  = self._fresh("__end")
        tmp_step = self._fresh("__step")

        # Emit: let __end = end; let __step = step; let var = start
        init = HirBlock([
            HirLet(tmp_end,  HIR_UNKNOWN, end),
            HirLet(tmp_step, HIR_UNKNOWN, step),
            HirLet(var,      HIR_INT,     start),
        ])

        # Loop condition: var < __end (positive step) — simplified to single check
        # A full lowering would inspect step sign; here we emit a general form.
        cond = HirBinOp("<", HirLoad(var), HirLoad(tmp_end), HIR_BOOL)

        # Body + increment
        body_stmts = self._block(node.block).stmts
        body_stmts.append(HirAssign(
            var,
            HirBinOp("+", HirLoad(var), HirLoad(tmp_step), HIR_INT)
        ))

        return HirBlock(init.stmts + [HirWhile(cond, HirBlock(body_stmts))])

    def lower_ForEachNode(self, node) -> HirBlock:
        """Desugar: for x in list → index-based while loop."""
        var     = node.var_name_token.value
        tmp_lst = self._fresh("__lst")
        tmp_len = self._fresh("__len")
        tmp_idx = self._fresh("__idx")

        iterable = self.lower(node.iterable_node)

        init = HirBlock([
            HirLet(tmp_lst, HIR_UNKNOWN, iterable),
            HirLet(tmp_len, HIR_INT,     HirCall("len", [HirLoad(tmp_lst)], return_type=HIR_INT)),
            HirLet(tmp_idx, HIR_INT,     HirLiteral(0, HIR_INT)),
        ])

        cond = HirBinOp("<", HirLoad(tmp_idx), HirLoad(tmp_len), HIR_BOOL)

        body_stmts = [
            HirLet(var, HIR_UNKNOWN, HirIndex(HirLoad(tmp_lst), HirLoad(tmp_idx))),
        ]
        body_stmts.extend(self._block(node.block).stmts)
        body_stmts.append(HirAssign(
            tmp_idx,
            HirBinOp("+", HirLoad(tmp_idx), HirLiteral(1, HIR_INT), HIR_INT)
        ))

        return HirBlock(init.stmts + [HirWhile(cond, HirBlock(body_stmts))])

    # ── Switch / Match (desugar to if/elif/else) ──────────────────────────────

    def lower_SwitchNode(self, node) -> HirBlock:
        """Desugar switch/case to an if/elif/else chain."""
        tmp = self._fresh("__sw")
        subject = HirLet(tmp, HIR_UNKNOWN, self.lower(node.subject_node))

        # Build from last case backwards
        else_block: Optional[HirBlock] = None
        if node.else_block:
            else_block = self._block(node.else_block)

        for value_nodes, body in reversed(node.cases):
            # Multiple values in one case: case a, b → if tmp==a or tmp==b
            if len(value_nodes) == 1:
                cond = HirBinOp("==", HirLoad(tmp), self.lower(value_nodes[0]), HIR_BOOL)
            else:
                cond = HirBinOp("==", HirLoad(tmp), self.lower(value_nodes[0]), HIR_BOOL)
                for vn in value_nodes[1:]:
                    cond = HirBinOp(
                        "or", cond,
                        HirBinOp("==", HirLoad(tmp), self.lower(vn), HIR_BOOL),
                        HIR_BOOL
                    )
            then = self._block(body)
            else_block = HirBlock([HirIf(cond, then, else_block)])

        stmts = [subject]
        if else_block:
            stmts.extend(else_block.stmts)
        return HirBlock(stmts)

    def lower_MatchNode(self, node) -> Any:
        """Desugar match expr { pattern => result } to if/elif/else."""
        tmp = self._fresh("__match")
        subject = HirLet(tmp, HIR_UNKNOWN, self.lower(node.subject_node))

        # Build nested ifs from last arm backwards
        result: Optional[HirBlock] = None

        for patterns, result_node in reversed(node.arms):
            lowered_result = self.lower(result_node)
            then = HirBlock([lowered_result])
            if patterns is None:
                # Wildcard arm (_) → always matches
                result = then
            else:
                cond = HirBinOp("==", HirLoad(tmp), self.lower(patterns[0]), HIR_BOOL)
                for p in patterns[1:]:
                    cond = HirBinOp(
                        "or", cond,
                        HirBinOp("==", HirLoad(tmp), self.lower(p), HIR_BOOL),
                        HIR_BOOL
                    )
                result = HirBlock([HirIf(cond, then, result)])

        stmts = [subject]
        if result:
            stmts.extend(result.stmts if isinstance(result, HirBlock) else [result])
        return HirBlock(stmts)

    # ── Null coalesce / ternary ────────────────────────────────────────────────

    def lower_NullCoalesceNode(self, node) -> Any:
        """Desugar x ?? y → if x != null { x } else { y }."""
        tmp  = self._fresh("__nc")
        left = self.lower(node.left)
        # Evaluate left once; if not null, use it, else use right
        return HirBlock([
            HirLet(tmp, HIR_UNKNOWN, left),
            HirIf(
                cond=HirBinOp("!=", HirLoad(tmp), HirLiteral(None, HIR_NULL), HIR_BOOL),
                then_block=HirBlock([HirLoad(tmp)]),
                else_block=HirBlock([self.lower(node.right)]),
            )
        ])

    def lower_TernaryNode(self, node) -> HirIf:
        """Desugar a if cond else b → if cond { a } else { b }."""
        return HirIf(
            cond=self.lower(node.condition_node),
            then_block=HirBlock([self.lower(node.value_node)]),
            else_block=HirBlock([self.lower(node.else_node)]),
        )

    # ── Function / lambda ──────────────────────────────────────────────────────

    def lower_FuncDefNode(self, node) -> HirFuncDef:
        params = []
        types  = list(node.arg_types or [])
        for i, tok in enumerate(node.arg_tokens):
            ptype = (types[i] if i < len(types) else None) or HIR_UNKNOWN
            params.append((tok.value, ptype))
        body = self._block(node.block)
        return HirFuncDef(
            name=node.name_token.value if node.name_token else None,
            params=params,
            return_type=node.return_type or HIR_UNKNOWN,
            body=body,
            is_variadic=bool(node.variadic),
            is_multi_return=self._analyze_multi_return(body),
        )

    def lower_LambdaNode(self, node) -> HirFuncDef:
        params = [(t.value, HIR_UNKNOWN) for t in node.param_tokens]
        body   = HirBlock([HirReturn(self.lower(node.expr_node))])
        return HirFuncDef(
            name=None,
            params=params,
            return_type=HIR_UNKNOWN,
            body=body,
            is_multi_return=self._analyze_multi_return(body),
        )

    def lower_AnonFuncNode(self, node) -> HirFuncDef:
        params = [(t.value, HIR_UNKNOWN) for t in node.param_tokens]
        body   = self._block(node.block)
        return HirFuncDef(
            name=None,
            params=params,
            return_type=HIR_UNKNOWN,
            body=body,
            is_multi_return=self._analyze_multi_return(body),
        )

    def lower_ReturnNode(self, node) -> HirReturn:
        val = self.lower(node.expression_node) if node.expression_node else None
        return HirReturn(val)

    # ── Calls ─────────────────────────────────────────────────────────────────

    def lower_CallNode(self, node) -> Any:
        func_name = node.func_name_token.value
        args   = [self.lower(a) for a in node.arguments]
        kwargs = {k: self.lower(v) for k, v in node.kwargs.items()}

        # instanceof(obj, ClassName) → HirIsInstance for the compiler.
        # The second argument must be a bare class name (VarAccessNode).
        if (func_name == "instanceof" and len(node.arguments) == 2
                and type(node.arguments[1]).__name__ == "VarAccessNode"):
            cls_name = node.arguments[1].token.value
            return HirIsInstance(obj=args[0], class_name=cls_name)

        # All other calls — class constructors are recognised later by the
        # codegen, which checks func_name against its registered class map.
        return HirCall(func_name, args, kwargs)

    def lower_ExprCallNode(self, node) -> HirExprCall:
        args   = [self.lower(a) for a in node.arguments]
        kwargs = {k: self.lower(v) for k, v in node.kwargs.items()}
        return HirExprCall(self.lower(node.callee_node), args, kwargs)

    def lower_MethodCallNode(self, node) -> Any:
        """Desugar obj.method(args).

        Known built-in dot-methods → HirCall(builtin_name, [obj, *args]).
        User-defined class methods  → HirObjectCall(obj, method, args).
        """
        obj    = self.lower(node.obj_node)
        args   = [self.lower(a) for a in node.arguments]
        kwargs = {k: self.lower(v) for k, v in node.kwargs.items()}
        method = node.method_token.value

        _METHOD_MAP = {
            "append": "append", "pop": "pop", "insert": "insert",
            "sort": "sort",     "reverse": "reverse",
            "keys":  "keys",    "values": "values",
            "len":   "len",     "contains": "contains", "remove": "remove",
            "upper": "upper",   "lower": "lower",
            "trim":  "trim",    "split": "split", "find": "find",
            "replace": "replace",
            "starts_with": "starts_with", "ends_with": "ends_with",
        }

        if method in _METHOD_MAP:
            return HirCall(_METHOD_MAP[method], [obj] + args, kwargs)

        # User-defined method — dispatch at runtime via the class registry.
        return HirObjectCall(obj=obj, method=method, args=args)

    # ── Attribute access ──────────────────────────────────────────────────────

    def lower_AttributeAccessNode(self, node) -> HirFieldLoad:
        return HirFieldLoad(self.lower(node.obj_node), node.attr_token.value)

    def lower_AttributeAssignNode(self, node) -> HirFieldStore:
        return HirFieldStore(
            obj=self.lower(node.obj_node),
            field=node.attr_token.value,
            value=self.lower(node.value_node),
        )

    # ── Indexing / slicing ────────────────────────────────────────────────────

    def lower_IndexAccessNode(self, node) -> HirIndex:
        return HirIndex(self.lower(node.base_node), self.lower(node.index_node))

    def lower_IndexAssignNode(self, node) -> HirIndexStore:
        return HirIndexStore(
            collection=self.lower(node.base_node),
            index=self.lower(node.index_node),
            value=self.lower(node.value_node),
        )

    def lower_SliceNode(self, node) -> HirCall:
        """Desugar slice[s:e:k] → __slice(obj, start, end, step)."""
        base  = self.lower(node.base_node)
        start = self.lower(node.start_node) if node.start_node else HirLiteral(None, HIR_NULL)
        end   = self.lower(node.end_node)   if node.end_node   else HirLiteral(None, HIR_NULL)
        step  = self.lower(node.step_node)  if node.step_node  else HirLiteral(1, HIR_INT)
        return HirCall("__slice", [base, start, end, step])

    # ── OOP ───────────────────────────────────────────────────────────────────

    def lower_ClassDefNode(self, node) -> HirClassDef:
        methods = [self.lower(m) for m in node.methods]
        return HirClassDef(
            name=node.name_token.value,
            parent=node.parent_token.value if node.parent_token else None,
            methods=methods,
        )

    def lower_StructDefNode(self, node) -> HirStructDef:
        fields = [
            (tok.value, type_name or HIR_UNKNOWN, self.lower(default) if default else None)
            for tok, type_name, default in node.fields
        ]
        return HirStructDef(name=node.name_token.value, fields=fields)

    # ── Imports ───────────────────────────────────────────────────────────────

    def lower_ImportNode(self, node) -> HirImport:
        alias = node.alias.value if node.alias else None
        names = [t.value for t in node.names] if node.names else []
        return HirImport(path=node.path, alias=alias, names=names)

    # ── Errors ────────────────────────────────────────────────────────────────

    def lower_AttemptRescueNode(self, node) -> HirAttemptRescue:
        error_var = node.error_var_token.value if node.error_var_token else None
        finally_b = self._block(node.finally_block) if node.finally_block else None
        return HirAttemptRescue(
            try_block=self._block(node.try_block),
            error_var=error_var,
            rescue_block=self._block(node.catch_block),
            finally_block=finally_b,
        )

    def lower_AlertNode(self, node) -> HirAlert:
        return HirAlert(self.lower(node.expression_node))

    # ── List comprehension ────────────────────────────────────────────────────

    def lower_ListCompNode(self, node) -> HirBlock:
        """Desugar [expr for x in iterable if cond] → while loop building a list."""
        tmp_result = self._fresh("__lc")
        stmts = [HirLet(tmp_result, HIR_LIST, HirList([]))]

        # Build nested for-each loops for each clause
        inner_stmts: list = []
        if node.condition:
            cond_check = self.lower(node.condition)
            inner_stmts.append(HirIf(
                cond=cond_check,
                then_block=HirBlock([HirCall(
                    "append",
                    [HirLoad(tmp_result), self.lower(node.expr)]
                )]),
            ))
        else:
            inner_stmts.append(HirCall(
                "append",
                [HirLoad(tmp_result), self.lower(node.expr)]
            ))

        # Wrap in for-each loops (innermost first)
        for var_tok, iterable_node in reversed(node.clauses):
            var     = var_tok.value if hasattr(var_tok, 'value') else str(var_tok)
            tmp_lst = self._fresh("__lc_lst")
            tmp_len = self._fresh("__lc_len")
            tmp_idx = self._fresh("__lc_idx")
            loop_init = [
                HirLet(tmp_lst, HIR_UNKNOWN, self.lower(iterable_node)),
                HirLet(tmp_len, HIR_INT,     HirCall("len", [HirLoad(tmp_lst)], return_type=HIR_INT)),
                HirLet(tmp_idx, HIR_INT,     HirLiteral(0, HIR_INT)),
            ]
            body = [
                HirLet(var, HIR_UNKNOWN, HirIndex(HirLoad(tmp_lst), HirLoad(tmp_idx))),
            ] + inner_stmts + [
                HirAssign(tmp_idx, HirBinOp("+", HirLoad(tmp_idx), HirLiteral(1, HIR_INT), HIR_INT))
            ]
            inner_stmts = loop_init + [
                HirWhile(
                    HirBinOp("<", HirLoad(tmp_idx), HirLoad(tmp_len), HIR_BOOL),
                    HirBlock(body)
                )
            ]

        stmts.extend(inner_stmts)
        stmts.append(HirLoad(tmp_result))
        return HirBlock(stmts)

    # ── No-ops ────────────────────────────────────────────────────────────────

    def lower_BreakNode(self, _)    -> HirBreak:    return HirBreak()
    def lower_ContinueNode(self, _) -> HirContinue: return HirContinue()
    def lower_PassNode(self, _)     -> HirPass:     return HirPass()
