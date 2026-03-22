# parser.py
#
# The Parser is the second stage of the Luz interpreter pipeline.  It receives
# the flat list of Token objects produced by the Lexer and builds an Abstract
# Syntax Tree (AST) — a hierarchical data structure that represents the program's
# grammatical structure.
#
# Pipeline position:
#   list[Token] → [Parser.parse()] → list[ASTNode] → Interpreter
#
# Design: Recursive Descent
# ──────────────────────────
# The parser is a hand-written recursive-descent parser.  Each grammar rule is
# represented by a method.  Methods call each other recursively, mirroring the
# nested structure of the grammar.
#
# Operator Precedence (lowest → highest):
#   logical or  (or)
#   logical and (and)
#   logical not (not)
#   comparisons (== != < > <= >=)
#   addition / subtraction (+ -)
#   multiplication / division / modulo (* / // %)
#   exponentiation (**)           ← right-associative
#   unary minus, literals, grouping, identifiers, index access
#
# Each precedence level is a separate method (logical_or → logical_and → … →
# factor).  Higher-precedence operators are parsed deeper in the call chain,
# which automatically gives them tighter binding.
#
# AST Nodes
# ─────────
# Every syntactic construct maps to a dedicated node class defined at the top
# of this file.  Node classes are intentionally simple data containers — all
# evaluation logic lives in the Interpreter.  Each node stores a `line`
# attribute (attached after construction) so the interpreter can report the
# source line when an error occurs at runtime.

from .tokens import TokenType, Token
from .exceptions import (
    UnexpectedTokenFault, UnexpectedEOFault, StructureFault,
    ParseFault, ExpressionFault, OperatorFault, SyntaxFault
)


# ── AST Node classes ──────────────────────────────────────────────────────────
# One class per distinct syntactic construct.  __repr__ methods exist purely
# for debugging — they are never called during normal interpretation.

# Represents an integer or float literal value.
class NumberNode:
    def __init__(self, token):
        self.token = token
    def __repr__(self): return f"{self.token.value}"

# Represents a string literal value.
class StringNode:
    def __init__(self, token):
        self.token = token
    def __repr__(self): return f"\"{self.token.value}\""

# Represents a format string: $"Hello {name}, you are {age} years old"
# parts is a list of alternating str (literal segments) and ASTNode (expressions).
class FStringNode:
    def __init__(self, parts):
        self.parts = parts

# Represents a boolean literal (true / false).
class BooleanNode:
    def __init__(self, token):
        self.token = token
    def __repr__(self): return f"{self.token.type.name.lower()}"

# Represents the null literal.
class NullNode:
    def __repr__(self): return "null"

# Represents multiple values packed together: used for `return a, b` and as
# the implicit RHS of a destructuring assignment.
class TupleNode:
    def __init__(self, elements):
        self.elements = elements  # List of AST nodes
    def __repr__(self): return f"({', '.join(repr(e) for e in self.elements)})"

# Represents destructuring assignment: x, y = expr
# var_tokens is a list of IDENTIFIER tokens; value_node is the RHS expression.
class DestructureAssignNode:
    def __init__(self, var_tokens, value_node):
        self.var_tokens = var_tokens
        self.value_node = value_node
    def __repr__(self): return f"({', '.join(t.value for t in self.var_tokens)} = {self.value_node})"

class DictDestructureAssignNode:
    def __init__(self, key_tokens, value_node):
        self.key_tokens = key_tokens   # list of IDENTIFIER tokens (used as both key and var name)
        self.value_node = value_node
    def __repr__(self): return f"({{{', '.join(t.value for t in self.key_tokens)}}} = {self.value_node})"

# Represents a ternary expression:  value if condition else other
# Evaluates condition; if truthy returns value_node, otherwise else_node.
class TernaryNode:
    def __init__(self, value_node, condition_node, else_node):
        self.value_node = value_node
        self.condition_node = condition_node
        self.else_node = else_node
    def __repr__(self): return f"({self.value_node} if {self.condition_node} else {self.else_node})"

class NullCoalesceNode:
    def __init__(self, left, right):
        self.left = left
        self.right = right
    def __repr__(self): return f"({self.left} ?? {self.right})"

# Represents a list literal: [expr, expr, …]
class ListNode:
    def __init__(self, elements):
        self.elements = elements  # List of AST nodes, one per element
    def __repr__(self): return f"{self.elements}"

class ListCompNode:
    def __init__(self, expr, var_token, iterable, condition=None):
        self.expr = expr            # Output expression
        self.var_token = var_token  # Loop variable token
        self.iterable = iterable    # Iterable expression
        self.condition = condition  # Optional filter (if clause)
    def __repr__(self): return f"[{self.expr} for {self.var_token.value} in {self.iterable}]"

# Represents a dictionary literal: {key: value, …}
class DictNode:
    def __init__(self, pairs):
        self.pairs = pairs  # List of (key_node, value_node) tuples
    def __repr__(self): return f"{{{self.pairs}}}"

# Represents reading a value via subscript: expr[index]
# After evaluation base_node and index_node are both evaluated, then the
# interpreter performs the actual lookup depending on the container type.
class IndexAccessNode:
    def __init__(self, base_node, index_node):
        self.base_node = base_node
        self.index_node = index_node
    def __repr__(self): return f"{self.base_node}[{self.index_node}]"

# Represents writing to a subscript position: expr[index] = value
# This is a statement-level construct; the interpreter mutates the container
# in-place rather than returning a new value.
class IndexAssignNode:
    def __init__(self, base_node, index_node, value_node):
        self.base_node = base_node
        self.index_node = index_node
        self.value_node = value_node
    def __repr__(self): return f"({self.base_node}[{self.index_node}] = {self.value_node})"

# Represents a unary operation: -expr or not expr
class UnaryOpNode:
    def __init__(self, op_token, node):
        self.op_token = op_token  # The operator token (MINUS or NOT)
        self.node = node          # The operand
    def __repr__(self): return f"({self.op_token.type.name} {self.node})"

# Represents reading a variable: just its name.
class VarAccessNode:
    def __init__(self, token):
        self.token = token  # The IDENTIFIER token (carries the name as .value)
    def __repr__(self): return f"{self.token.value}"

# Represents assigning to a variable: name = expr
class VarAssignNode:
    def __init__(self, var_name_token, value_node):
        self.var_name_token = var_name_token
        self.value_node = value_node
    def __repr__(self): return f"({self.var_name_token.value} = {self.value_node})"

# Represents a binary operation: left op right  (e.g. a + b, x == y)
class BinOpNode:
    def __init__(self, left_node, op_token, right_node):
        self.left_node = left_node
        self.op_token = op_token
        self.right_node = right_node
    def __repr__(self): return f"({self.left_node} {self.op_token.type.name} {self.right_node})"

# Represents an if / elif* / else? chain.
# cases is a list of (condition_node, block) pairs — one per if/elif branch.
# else_case is a block (list of statements) or None.
class IfNode:
    def __init__(self, cases, else_case):
        self.cases = cases        # [(condition, block), …]
        self.else_case = else_case

# Represents a while loop: while condition { block }
class WhileNode:
    def __init__(self, condition_node, block):
        self.condition_node = condition_node
        self.block = block  # List of statement nodes

# Represents a for loop with a numeric range: for var = start to end { block }
# The loop variable is scoped to the loop body.
class ForNode:
    def __init__(self, var_name_token, start_value_node, end_value_node, block, step_node=None):
        self.var_name_token = var_name_token
        self.start_value_node = start_value_node
        self.end_value_node = end_value_node
        self.step_node = step_node  # None means default step of 1
        self.block = block

# Represents a for-each loop over a collection: for item in expr { block }
# Works with lists, strings (iterates characters), and dicts (iterates keys).
class ForEachNode:
    def __init__(self, var_name_token, iterable_node, block):
        self.var_name_token = var_name_token
        self.iterable_node = iterable_node
        self.block = block

# Represents a lambda (short form):  fn(x, y) => expr
# The expression is implicitly returned — no `return` needed.
class LambdaNode:
    def __init__(self, param_tokens, expr_node):
        self.param_tokens = param_tokens
        self.expr_node = expr_node

# Represents an anonymous function (long form):  fn(x, y) { body }
# Behaves exactly like a named function but has no name.
class AnonFuncNode:
    def __init__(self, param_tokens, block):
        self.param_tokens = param_tokens
        self.block = block

# Represents a function definition: function name(args) { block }
# arg_tokens is a list of IDENTIFIER tokens (the parameter names).
# defaults is a parallel list: None means required, an ASTNode means optional.
# variadic: if True, the last parameter collects all remaining arguments as a list.
class FuncDefNode:
    def __init__(self, name_token, arg_tokens, block, defaults=None, variadic=False):
        self.name_token = name_token
        self.arg_tokens = arg_tokens
        self.defaults = defaults if defaults is not None else [None] * len(arg_tokens)
        self.variadic = variadic  # True if the last param is ...name
        self.block = block

# Represents a return statement inside a function body.
# expression_node may be None for a bare `return`.
class ReturnNode:
    def __init__(self, expression_node):
        self.expression_node = expression_node

# Represents an import statement: import "path/to/file.luz"
class ImportNode:
    def __init__(self, file_path_token):
        self.file_path_token = file_path_token  # STRING token carrying the path

# Represents an attempt/rescue block (structured error handling).
# error_var_token is the IDENTIFIER token used to bind the error message inside
# the rescue body.
class AttemptRescueNode:
    def __init__(self, try_block, error_var_token, catch_block, finally_block=None):
        self.try_block = try_block
        self.error_var_token = error_var_token
        self.catch_block = catch_block
        self.finally_block = finally_block  # Optional — runs regardless of error

# Represents the `alert` statement — raises a user-defined error at runtime.
class AlertNode:
    def __init__(self, expression_node):
        self.expression_node = expression_node

# The following three node classes carry no data — their type alone is
# sufficient for the interpreter to know what to do.
class BreakNode:
    def __repr__(self): return "break"

class ContinueNode:
    def __repr__(self): return "continue"

class PassNode:
    def __repr__(self): return "pass"

# Represents a class definition: class Name { method ... }
# or with inheritance:          class Name extends Parent { method ... }
class ClassDefNode:
    def __init__(self, name_token, methods, parent_token=None):
        self.name_token = name_token
        self.parent_token = parent_token  # IDENTIFIER token for the parent class, or None
        self.methods = methods  # List of FuncDefNode

# Represents reading an attribute: obj.name
class AttributeAccessNode:
    def __init__(self, obj_node, attr_token):
        self.obj_node = obj_node
        self.attr_token = attr_token
    def __repr__(self): return f"{self.obj_node}.{self.attr_token.value}"

# Represents writing an attribute: obj.name = value
class AttributeAssignNode:
    def __init__(self, obj_node, attr_token, value_node):
        self.obj_node = obj_node
        self.attr_token = attr_token
        self.value_node = value_node
        
# Represents a switch statement:
#   switch expr { case v1, v2 { block } … else { block } }
# cases: list of (value_nodes, block) — each case can match multiple values.
# else_block: optional fallback block (None if absent).
class SwitchNode:
    def __init__(self, subject_node, cases, else_block):
        self.subject_node = subject_node
        self.cases = cases        # [(value_nodes, block), …]
        self.else_block = else_block

# Represents a match expression:
#   match expr { pattern, … => expr  …  _ => expr }
# arms: list of (pattern_nodes_or_None, result_node)
#   pattern_nodes_or_None is None for the wildcard arm (_).
# Returns the result_node of the first matched arm.
class MatchNode:
    def __init__(self, subject_node, arms):
        self.subject_node = subject_node
        self.arms = arms  # [(pattern_nodes | None, result_node), …]

class MethodCallNode:
    def __init__(self, obj_node, method_token, arguments, kwargs=None):
        self.obj_node = obj_node
        self.method_token = method_token
        self.arguments = arguments
        self.kwargs = kwargs or {}   # {name: expr_node}

# Represents a function call: name(arg, arg, …)
# arguments is a list of AST nodes (the evaluated argument expressions).
class CallNode:
    def __init__(self, func_name_token, arguments, kwargs=None):
        self.func_name_token = func_name_token
        self.arguments = arguments
        self.kwargs = kwargs or {}   # {name: expr_node}
    def __repr__(self): return f"{self.func_name_token.value}({self.arguments})"


# ── Parser ────────────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.current_token = self.tokens[self.pos]

    # advance() moves to the next token in the list.  The bounds check ensures
    # that current_token stays at EOF rather than raising an IndexError when the
    # parser tries to look past the end of the list.
    def advance(self):
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current_token = self.tokens[self.pos]

    # parse() is the public entry point.  It delegates to statements() and
    # wraps unexpected Python exceptions into a ParseFault so callers always
    # receive a LuzError on failure, never a raw Python traceback.
    # Known SyntaxFault subclasses are re-raised as-is to preserve their type.
    def parse(self):
        try:
            return self.statements()
        except UnexpectedTokenFault as e:
            raise e
        except SyntaxFault as e:
            raise e
        except Exception as e:
            raise ParseFault(f"Error while parsing code: {str(e)}")

    # statements() collects a sequence of statements until it hits EOF or a
    # closing brace '}'.  The RBRACE check allows this same method to parse
    # both top-level programs and the bodies of blocks (if, while, function, …).
    def statements(self):
        statements = []
        while self.current_token.type != TokenType.EOF and self.current_token.type != TokenType.RBRACE:
            statements.append(self.statement())
        return statements

    # statement() recognises the opening token of each statement form and
    # dispatches to the appropriate parsing method.  For constructs that don't
    # have a distinctive leading keyword (expressions, assignments) it falls
    # through to expr() at the bottom.
    def statement(self):
        if self.current_token.type == TokenType.IF:
            return self.if_expr()

        if self.current_token.type == TokenType.WHILE:
            return self.while_expr()

        if self.current_token.type == TokenType.FOR:
            return self.for_expr()

        if self.current_token.type == TokenType.FUNCTION:
            return self.func_def()

        if self.current_token.type == TokenType.RETURN:
            line = self.current_token.line
            self.advance()
            # `return` with no expression is valid — the function returns None.
            # We stop at RBRACE or EOF rather than trying to parse a non-existent expr.
            expr = None
            if self.current_token.type not in (TokenType.EOF, TokenType.RBRACE):
                expr = self.expr()
                # `return a, b, c` — pack multiple values into a TupleNode
                if self.current_token.type == TokenType.COMMA:
                    values = [expr]
                    while self.current_token.type == TokenType.COMMA:
                        self.advance()  # Consume ','
                        values.append(self.expr())
                    expr = TupleNode(values); expr.line = line
            node = ReturnNode(expr); node.line = line
            return node

        if self.current_token.type == TokenType.IMPORT:
            line = self.current_token.line
            self.advance()
            if self.current_token.type != TokenType.STRING:
                raise UnexpectedTokenFault(f"Expected module path string after 'import', received {self.current_token}")
            path_token = self.current_token
            self.advance()
            node = ImportNode(path_token); node.line = line
            return node

        if self.current_token.type == TokenType.ATTEMPT:
            return self.attempt_rescue_expr()

        if self.current_token.type == TokenType.ALERT:
            line = self.current_token.line
            self.advance()
            expr = self.expr()
            node = AlertNode(expr); node.line = line
            return node

        if self.current_token.type == TokenType.BREAK:
            line = self.current_token.line
            self.advance()
            node = BreakNode(); node.line = line
            return node

        if self.current_token.type == TokenType.CONTINUE:
            line = self.current_token.line
            self.advance()
            node = ContinueNode(); node.line = line
            return node

        if self.current_token.type == TokenType.PASS:
            line = self.current_token.line
            self.advance()
            node = PassNode(); node.line = line
            return node
        
        if self.current_token.type == TokenType.CLASS:
            return self.class_def()

        if self.current_token.type == TokenType.SWITCH:
            return self.switch_stmt()

        if self.current_token.type == TokenType.MATCH:
            return self.match_expr()

        COMPOUND = {
            TokenType.PLUS_ASSIGN:  TokenType.PLUS,
            TokenType.MINUS_ASSIGN: TokenType.MINUS,
            TokenType.MUL_ASSIGN:   TokenType.MUL,
            TokenType.DIV_ASSIGN:   TokenType.DIV,
            TokenType.MOD_ASSIGN:   TokenType.MOD,
            TokenType.POW_ASSIGN:   TokenType.POW,
        }

        # Dict destructuring: {name, age} = expr
        # Lookahead: { (IDENTIFIER COMMA)* IDENTIFIER } =
        if self.current_token.type == TokenType.LBRACE:
            if self._is_dict_destructure():
                return self.dict_destructure_assign()

        if self.current_token.type == TokenType.IDENTIFIER:
            # Check for destructuring assignment: x, y, z = expr
            # Scan ahead to confirm the pattern is IDENTIFIER (COMMA IDENTIFIER)+ ASSIGN
            next_token = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            if next_token and next_token.type == TokenType.COMMA:
                i = self.pos
                while i < len(self.tokens) and self.tokens[i].type == TokenType.IDENTIFIER:
                    i += 1
                    if i < len(self.tokens) and self.tokens[i].type == TokenType.COMMA:
                        i += 1
                    else:
                        break
                if i < len(self.tokens) and self.tokens[i].type == TokenType.ASSIGN:
                    line = self.current_token.line
                    var_tokens = []
                    while self.current_token.type == TokenType.IDENTIFIER:
                        var_tokens.append(self.current_token)
                        self.advance()
                        if self.current_token.type == TokenType.COMMA:
                            self.advance()
                        else:
                            break
                    self.advance()  # Consume '='
                    rhs = self.expr()
                    node = DestructureAssignNode(var_tokens, rhs); node.line = line
                    return node

            # One-token lookahead: if the token after the identifier is '=' or
            # a compound assignment operator, handle it before entering expr().
            next_token = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            if next_token and next_token.type == TokenType.ASSIGN:
                var_name = self.current_token
                self.advance()  # Consume the identifier
                self.advance()  # Consume '='
                expr = self.expr()
                node = VarAssignNode(var_name, expr); node.line = var_name.line
                return node

            if next_token and next_token.type in COMPOUND:
                var_name = self.current_token
                self.advance()  # Consume the identifier
                op_token = self.current_token
                op_token = op_token.__class__(COMPOUND[op_token.type], None, op_token.line)
                self.advance()  # Consume the compound operator
                rhs = self.expr()
                # Desugar: x += e  →  x = x + e
                left = VarAccessNode(var_name); left.line = var_name.line
                binop = BinOpNode(left, op_token, rhs); binop.line = var_name.line
                node = VarAssignNode(var_name, binop); node.line = var_name.line
                return node

        # Fall through: parse as a general expression (function call, arithmetic, …)
        node = self.expr()

        # Post-expression check for index assignment: lista[0] = 5
        if isinstance(node, IndexAccessNode) and self.current_token.type == TokenType.ASSIGN:
            line = node.line
            self.advance()  # Consume '='
            value = self.expr()
            assign_node = IndexAssignNode(node.base_node, node.index_node, value)
            assign_node.line = line
            return assign_node

        # Post-expression check for attribute assignment: obj.attr = value
        if isinstance(node, AttributeAccessNode) and self.current_token.type == TokenType.ASSIGN:
            line = node.line
            self.advance()  # Consume '='
            value = self.expr()
            assign_node = AttributeAssignNode(node.obj_node, node.attr_token, value)
            assign_node.line = line
            return assign_node

        return node

    # attempt_rescue_expr() parses the structured error-handling construct:
    #   attempt { statements } rescue (err) { statements }
    # The error variable is bound in the rescue scope to the string
    # representation of whatever error was caught.
    def attempt_rescue_expr(self):
        line = self.current_token.line
        self.advance()  # Consume 'attempt'
        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{' after attempt")
        self.advance()  # Consume '{'

        try_block = self.statements()

        if self.current_token.type == TokenType.EOF:
            raise UnexpectedEOFault("Unexpected end of file in attempt block")
        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault(f"Expected '}}' at the end of attempt block, received {self.current_token}")
        self.advance()  # Consume '}'

        if self.current_token.type != TokenType.RESCUE:
            raise StructureFault("Expected 'rescue' after attempt block")
        self.advance()  # Consume 'rescue'

        if self.current_token.type != TokenType.LPAREN:
            raise StructureFault("Expected '(' after rescue")
        self.advance()  # Consume '('

        if self.current_token.type != TokenType.IDENTIFIER:
            raise UnexpectedTokenFault("Expected error variable name in rescue")
        error_var = self.current_token
        self.advance()  # Consume the error variable name

        if self.current_token.type != TokenType.RPAREN:
            raise UnexpectedTokenFault("Expected ')'")
        self.advance()  # Consume ')'

        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{' for rescue block")
        self.advance()  # Consume '{'

        catch_block = self.statements()

        if self.current_token.type == TokenType.EOF:
            raise UnexpectedEOFault("Unexpected end of file in rescue block")
        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault(f"Expected '}}' at the end of rescue block, received {self.current_token}")
        self.advance()  # Consume '}'

        finally_block = None
        if self.current_token.type == TokenType.FINALLY:
            self.advance()  # Consume 'finally'
            if self.current_token.type != TokenType.LBRACE:
                raise StructureFault("Expected '{' after finally")
            self.advance()  # Consume '{'
            finally_block = self.statements()
            if self.current_token.type != TokenType.RBRACE:
                raise UnexpectedTokenFault("Expected '}' at end of finally block")
            self.advance()  # Consume '}'

        node = AttemptRescueNode(try_block, error_var, catch_block, finally_block); node.line = line
        return node

    # func_def() parses:  function name(param, …) { body }
    # Parameters are just identifier names at parse time; their values are
    # bound by LuzFunction.__call__() at call time.
    def func_def(self):
        line = self.current_token.line
        self.advance()  # Consume 'function'
        if self.current_token.type != TokenType.IDENTIFIER:
            raise UnexpectedTokenFault("Expected function name")
        name_token = self.current_token
        self.advance()  # Consume the name

        if self.current_token.type != TokenType.LPAREN:
            raise StructureFault("Expected '('")
        self.advance()  # Consume '('

        # Parse the parameter list, which may be empty.
        # Both IDENTIFIER and SELF are valid parameter names (methods use `self`
        # as their first parameter to receive the instance at call time).
        # Parameters may have a default value: name = expr
        # A variadic parameter ...name must be last and cannot have a default.
        # All non-default parameters must precede default ones.
        arg_tokens = []
        defaults = []
        variadic = False

        def parse_one_param():
            """Parse a single param (name or ...name) and append to arg_tokens/defaults.
            Returns True if this was a variadic param (caller should stop looping)."""
            nonlocal variadic
            if self.current_token.type == TokenType.ELLIPSIS:
                self.advance()  # Consume '...'
                if self.current_token.type not in (TokenType.IDENTIFIER, TokenType.SELF):
                    raise UnexpectedTokenFault("Expected parameter name after '...'")
                arg_tokens.append(self.current_token)
                defaults.append(None)
                self.advance()
                variadic = True
                return True  # Must be last
            if self.current_token.type not in (TokenType.IDENTIFIER, TokenType.SELF):
                raise UnexpectedTokenFault("Expected argument name")
            arg_tokens.append(self.current_token)
            self.advance()
            if self.current_token.type == TokenType.ASSIGN:
                self.advance()
                defaults.append(self.expr())
            else:
                if any(d is not None for d in defaults):
                    raise StructureFault("Non-default parameter cannot follow a default parameter")
                defaults.append(None)
            return False

        if self.current_token.type in (TokenType.IDENTIFIER, TokenType.SELF, TokenType.ELLIPSIS):
            done = parse_one_param()
            while not done and self.current_token.type == TokenType.COMMA:
                self.advance()  # Consume ','
                done = parse_one_param()
            if variadic and self.current_token.type == TokenType.COMMA:
                raise StructureFault("Variadic parameter '...' must be the last parameter")

        if self.current_token.type != TokenType.RPAREN:
            raise UnexpectedTokenFault("Expected ')'")
        self.advance()  # Consume ')'

        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{'")
        self.advance()  # Consume '{'

        block = self.statements()

        if self.current_token.type == TokenType.EOF:
            raise UnexpectedEOFault("Unexpected end of file in function definition")
        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault("Expected '}'")
        self.advance()  # Consume '}'

        node = FuncDefNode(name_token, arg_tokens, block, defaults, variadic); node.line = line
        return node

    # switch_stmt() parses:
    #   switch <expr> {
    #       case v1, v2 { block }
    #       …
    #       else { block }
    #   }
    def switch_stmt(self):
        line = self.current_token.line
        self.advance()  # Consume 'switch'
        subject = self.expr()
        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{' after switch expression")
        self.advance()  # Consume '{'

        cases = []
        else_block = None
        while self.current_token.type not in (TokenType.RBRACE, TokenType.EOF):
            if self.current_token.type == TokenType.ELSE:
                self.advance()  # Consume 'else'
                if self.current_token.type != TokenType.LBRACE:
                    raise StructureFault("Expected '{' after else in switch")
                self.advance()
                else_block = self.statements()
                if self.current_token.type != TokenType.RBRACE:
                    raise UnexpectedTokenFault("Expected '}' after else block")
                self.advance()
                break  # else must be last
            if self.current_token.type != TokenType.CASE:
                raise UnexpectedTokenFault(f"Expected 'case' or 'else' in switch, got {self.current_token}")
            self.advance()  # Consume 'case'
            # One or more comma-separated values
            values = [self.expr()]
            while self.current_token.type == TokenType.COMMA:
                self.advance()
                values.append(self.expr())
            if self.current_token.type != TokenType.LBRACE:
                raise StructureFault("Expected '{' after case value(s)")
            self.advance()
            block = self.statements()
            if self.current_token.type != TokenType.RBRACE:
                raise UnexpectedTokenFault("Expected '}' after case block")
            self.advance()
            cases.append((values, block))

        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault("Expected '}' to close switch")
        self.advance()  # Consume closing '}'
        node = SwitchNode(subject, cases, else_block); node.line = line
        return node

    # match_expr() parses:
    #   match <expr> {
    #       v1, v2 => result_expr
    #       _      => result_expr
    #   }
    # Returns the result of the first matching arm.
    # `_` (underscore identifier) acts as the wildcard / default arm.
    def match_expr(self):
        line = self.current_token.line
        self.advance()  # Consume 'match'
        subject = self.expr()
        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{' after match expression")
        self.advance()  # Consume '{'

        arms = []
        while self.current_token.type not in (TokenType.RBRACE, TokenType.EOF):
            # Wildcard arm: _ => expr
            if (self.current_token.type == TokenType.IDENTIFIER and
                    self.current_token.value == '_'):
                self.advance()  # Consume '_'
                if self.current_token.type != TokenType.ARROW:
                    raise StructureFault("Expected '=>' after wildcard '_' in match")
                self.advance()
                result = self.expr()
                arms.append((None, result))
                break  # wildcard must be last
            # Normal arm: expr, expr, … => result
            patterns = [self.expr()]
            while self.current_token.type == TokenType.COMMA:
                self.advance()
                if (self.current_token.type == TokenType.IDENTIFIER and
                        self.current_token.value == '_'):
                    raise StructureFault("Wildcard '_' cannot be combined with other patterns")
                patterns.append(self.expr())
            if self.current_token.type != TokenType.ARROW:
                raise StructureFault("Expected '=>' after match pattern(s)")
            self.advance()  # Consume '=>'
            result = self.expr()
            arms.append((patterns, result))

        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault("Expected '}' to close match")
        self.advance()  # Consume '}'
        node = MatchNode(subject, arms); node.line = line
        return node

    def class_def(self):
        line = self.current_token.line
        self.advance()  # Consume 'class'
        if self.current_token.type != TokenType.IDENTIFIER:
            raise UnexpectedTokenFault("Expected class name")
        name_token = self.current_token
        self.advance()

        # Optional inheritance clause: extends ParentName
        parent_token = None
        if self.current_token.type == TokenType.EXTENDS:
            self.advance()  # Consume 'extends'
            if self.current_token.type != TokenType.IDENTIFIER:
                raise UnexpectedTokenFault("Expected parent class name after 'extends'")
            parent_token = self.current_token
            self.advance()

        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{' after class name")
        self.advance()  # Consume '{'
        methods = []
        while self.current_token.type != TokenType.RBRACE:
            if self.current_token.type == TokenType.EOF:
                raise UnexpectedEOFault("Unexpected end of file in class")
            if self.current_token.type != TokenType.FUNCTION:
                raise UnexpectedTokenFault("Expected method definition inside class")
            methods.append(self.func_def())
        self.advance()  # Consume '}'
        node = ClassDefNode(name_token, methods, parent_token); node.line = line
        return node

    # if_expr() parses the full if / elif* / else? chain into a single IfNode.
    # All branches are collected into the same node so the interpreter can
    # evaluate them sequentially without needing to recurse.
    def if_expr(self):
        line = self.current_token.line
        cases = []
        else_case = None

        self.advance()  # Consume 'if'
        condition = self.expr()
        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{' after if condition")
        self.advance()
        block = self.statements()
        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault("Expected '}' after if block")
        self.advance()
        cases.append((condition, block))

        # Collect zero or more elif branches.
        while self.current_token.type == TokenType.ELIF:
            self.advance()  # Consume 'elif'
            condition = self.expr()
            if self.current_token.type != TokenType.LBRACE:
                raise StructureFault("Expected '{' after elif condition")
            self.advance()
            block = self.statements()
            if self.current_token.type != TokenType.RBRACE:
                raise UnexpectedTokenFault("Expected '}' after elif block")
            self.advance()
            cases.append((condition, block))

        # Optional else branch.
        if self.current_token.type == TokenType.ELSE:
            self.advance()  # Consume 'else'
            if self.current_token.type != TokenType.LBRACE:
                raise StructureFault("Expected '{' after else")
            self.advance()
            else_case = self.statements()
            if self.current_token.type != TokenType.RBRACE:
                raise UnexpectedTokenFault("Expected '}' after else block")
            self.advance()

        node = IfNode(cases, else_case); node.line = line
        return node

    # while_expr() parses:  while condition { body }
    def while_expr(self):
        line = self.current_token.line
        self.advance()  # Consume 'while'
        condition = self.expr()
        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{' after while condition")
        self.advance()
        block = self.statements()
        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault("Expected '}' after while block")
        self.advance()
        node = WhileNode(condition, block); node.line = line
        return node

    # for_expr() handles two loop forms:
    #   Range loop:   for i = 0 to 10 { … }
    #   For-each:     for item in list { … }
    # After consuming the variable name, a one-token lookahead decides which form.
    def for_expr(self):
        line = self.current_token.line
        self.advance()  # Consume 'for'
        if self.current_token.type != TokenType.IDENTIFIER:
            raise UnexpectedTokenFault("Expected variable name after 'for'")
        var_name = self.current_token
        self.advance()

        if self.current_token.type == TokenType.IN:
            # for-each: for item in <iterable> { body }
            self.advance()  # Consume 'in'
            iterable = self.expr()
            if self.current_token.type != TokenType.LBRACE:
                raise StructureFault("Expected '{' after for-each iterable")
            self.advance()
            block = self.statements()
            if self.current_token.type != TokenType.RBRACE:
                raise UnexpectedTokenFault("Expected '}' after for block")
            self.advance()
            node = ForEachNode(var_name, iterable, block); node.line = line
            return node

        # Range loop: for i = start to end { body }
        if self.current_token.type != TokenType.ASSIGN:
            raise StructureFault("Expected '=' or 'in' after for variable")
        self.advance()  # Consume '='
        start_value = self.expr()
        if self.current_token.type != TokenType.TO:
            raise StructureFault("Expected 'to' after for start value")
        self.advance()  # Consume 'to'
        end_value = self.expr()
        step_node = None
        if self.current_token.type == TokenType.STEP:
            self.advance()  # Consume 'step'
            step_node = self.expr()
        if self.current_token.type != TokenType.LBRACE:
            raise StructureFault("Expected '{' after for range")
        self.advance()
        block = self.statements()
        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault("Expected '}' after for block")
        self.advance()
        node = ForNode(var_name, start_value, end_value, block, step_node); node.line = line
        return node

    # ── Expression parsing (operator-precedence chain) ────────────────────────
    # Each method handles one precedence level.  Lower-precedence operators are
    # parsed by methods higher in the call chain.  The chain is:
    #   expr → logical_or → logical_and → logical_not → comp_expr
    #       → arith_expr → term → power → factor

    def expr(self):
        # Top-level expression entry point.
        # Ternary has the lowest precedence: value if condition else other
        node = self.null_coalesce()
        # Only parse as ternary if 'else' appears before any unmatched '{'.
        # Without this check, `x = value\nif cond { }` would consume the
        # next statement's `if` as a ternary operator.
        if self.current_token.type == TokenType.IF and self._has_ternary_else():
            line = self.current_token.line
            self.advance()  # Consume 'if'
            condition = self.logical_or()
            if self.current_token.type != TokenType.ELSE:
                raise UnexpectedTokenFault("Expected 'else' in ternary expression")
            self.advance()  # Consume 'else'
            else_node = self.expr()  # Right-recursive for chaining
            ternary = TernaryNode(node, condition, else_node)
            ternary.line = line
            return ternary
        return node

    def _has_ternary_else(self):
        """Scan ahead from the current IF token to check if 'else' appears
        before a '{' at depth 0 (which would mean it is an if-statement, not
        a ternary).  Parentheses and brackets are tracked so that braces
        inside call arguments are not mistaken for block delimiters."""
        depth = 0
        i = self.pos + 1  # start after the IF token
        while i < len(self.tokens):
            t = self.tokens[i]
            if t.type == TokenType.EOF:
                return False
            if t.type == TokenType.LBRACE:
                if depth == 0:
                    return False  # block start at top level → if-statement
                depth += 1
            elif t.type == TokenType.RBRACE:
                depth -= 1
                if depth < 0:
                    return False
            elif t.type in (TokenType.LPAREN, TokenType.LBRACKET):
                depth += 1
            elif t.type in (TokenType.RPAREN, TokenType.RBRACKET):
                depth -= 1
            elif t.type == TokenType.ELSE and depth == 0:
                return True
            i += 1
        return False

    def null_coalesce(self):
        # `??` sits between ternary and logical_or.
        # Right-recursive so chaining works: a ?? b ?? c → a ?? (b ?? c)
        node = self.logical_or()
        if self.current_token.type == TokenType.NULL_COALESCE:
            line = self.current_token.line
            self.advance()
            right = self.null_coalesce()
            result = NullCoalesceNode(node, right)
            result.line = line
            return result
        return node

    def logical_or(self):
        # `or` has the lowest precedence of any binary operator.
        return self.bin_op(self.logical_and, (TokenType.OR,))

    def logical_and(self):
        return self.bin_op(self.logical_not, (TokenType.AND,))

    def logical_not(self):
        # `not` is a unary prefix operator.  Allowing logical_not() to call
        # itself recursively means `not not x` works naturally.
        if self.current_token.type == TokenType.NOT:
            op_token = self.current_token
            self.advance()
            return UnaryOpNode(op_token, self.logical_not())
        return self.comp_expr()

    def comp_expr(self):
        # All comparison operators share the same precedence level.
        # `in` and `not in` are handled here as membership tests.
        node = self.arith_expr()
        while True:
            if self.current_token.type in (TokenType.EE, TokenType.NE, TokenType.LT, TokenType.GT, TokenType.LTE, TokenType.GTE, TokenType.IN):
                op_token = self.current_token
                self.advance()
                right = self.arith_expr()
                bin_node = BinOpNode(node, op_token, right)
                bin_node.line = op_token.line
                node = bin_node
            elif self.current_token.type == TokenType.NOT:
                # Peek ahead: `not in` is a two-token membership operator
                next_pos = self.pos + 1
                if next_pos < len(self.tokens) and self.tokens[next_pos].type == TokenType.IN:
                    op_token = Token(TokenType.NOT_IN, None, self.current_token.line)
                    self.advance()  # Consume 'not'
                    self.advance()  # Consume 'in'
                    right = self.arith_expr()
                    bin_node = BinOpNode(node, op_token, right)
                    bin_node.line = op_token.line
                    node = bin_node
                else:
                    break
            else:
                break
        return node

    def arith_expr(self):
        # Addition and subtraction bind less tightly than multiplication.
        return self.bin_op(self.term, (TokenType.PLUS, TokenType.MINUS))

    def term(self):
        # Multiplication, division, integer division, and modulo all have equal
        # precedence and bind more tightly than addition/subtraction.
        return self.bin_op(self.power, (TokenType.MUL, TokenType.DIV, TokenType.IDIV, TokenType.MOD))

    def power(self):
        # Exponentiation is right-associative: 2**3**2 == 2**(3**2) == 512.
        # Right-associativity is achieved by recursing into power() again on the
        # right-hand side, rather than using the iterative bin_op helper (which
        # would produce a left-associative tree).
        base = self.factor()
        if self.current_token.type == TokenType.POW:
            op = self.current_token
            self.advance()
            exp = self.power()  # Recurse right → right-associative
            node = BinOpNode(base, op, exp)
            node.line = op.line
            return node
        return base

    def factor(self):
        # factor() handles the highest-precedence constructs:
        #   • unary minus
        #   • literal values (numbers, strings, booleans)
        #   • collection literals (lists, dicts)
        #   • parenthesised expressions
        #   • identifiers (which may be variable access or function calls)
        # After any of the above, a trailing '[' triggers index-access parsing
        # to handle chained subscripts: a[0][1][2]
        token = self.current_token
        node = None

        if token.type == TokenType.MATCH:
            return self.match_expr()

        if token.type == TokenType.MINUS:
            # Unary minus: recurse into factor() so that '--x' also works.
            self.advance()
            node = UnaryOpNode(token, self.factor())
            node.line = token.line
            return node

        if token.type in (TokenType.INT, TokenType.FLOAT):
            self.advance()
            node = NumberNode(token)
            node.line = token.line
        elif token.type == TokenType.STRING:
            self.advance()
            node = StringNode(token)
            node.line = token.line
        elif token.type == TokenType.FSTRING:
            self.advance()
            node = self._parse_fstring_parts(token)
            node.line = token.line
        elif token.type in (TokenType.TRUE, TokenType.FALSE):
            self.advance()
            node = BooleanNode(token)
            node.line = token.line
        elif token.type == TokenType.NULL:
            self.advance()
            node = NullNode()
            node.line = token.line
        elif token.type == TokenType.LBRACKET:
            node = self.list_literal()
        elif token.type == TokenType.LBRACE:
            node = self.dict_literal()
        elif token.type == TokenType.IDENTIFIER:
            # Could be a plain variable read or a function call — identifier_expr
            # peeks at the next token to decide.
            node = self.identifier_expr()
        elif token.type == TokenType.FN:
            node = self.lambda_or_anon()
            node.line = token.line
            return node
        elif token.type == TokenType.SELF:
            # `self` inside a method refers to the current instance.
            # It is treated as a variable access so that `self.attr` parsing
            # falls through to the DOT-chaining loop below.
            self.advance()
            node = VarAccessNode(token)
            node.line = token.line
        elif token.type == TokenType.LPAREN:
            # Parenthesised sub-expression for explicit grouping.
            self.advance()  # Consume '('
            node = self.expr()
            if self.current_token.type != TokenType.RPAREN:
                raise UnexpectedTokenFault("Expected ')'")
            self.advance()  # Consume ')'
        elif token.type == TokenType.EOF:
            raise UnexpectedEOFault("Unexpected end of expression")
        else:
            raise ExpressionFault(f"Invalid expression at token: {token}")

        # Handle zero or more chained index operations: base[i][j][k]…
        # Each iteration wraps the current node in a new IndexAccessNode.
        while self.current_token.type == TokenType.LBRACKET:
            bracket_line = self.current_token.line
            self.advance()  # Consume '['
            index = self.expr()
            if self.current_token.type != TokenType.RBRACKET:
                raise UnexpectedTokenFault("Expected ']'")
            self.advance()  # Consume ']'
            index_node = IndexAccessNode(node, index)
            index_node.line = bracket_line
            node = index_node

        # Handle zero or more chained dot accesses: obj.attr  or  obj.method(args)
        # This loop also handles chaining: obj.a.b.c()
        while self.current_token.type == TokenType.DOT:
            dot_line = self.current_token.line
            self.advance()  # Consume '.'
            if self.current_token.type != TokenType.IDENTIFIER:
                raise UnexpectedTokenFault("Expected attribute or method name after '.'")
            attr_token = self.current_token
            self.advance()  # Consume the attribute/method name
            if self.current_token.type == TokenType.LPAREN:
                # Method call: obj.method(args) or obj.method(name: val, …)
                self.advance()  # Consume '('
                args, kwargs = self.parse_call_args()
                if self.current_token.type != TokenType.RPAREN:
                    raise UnexpectedTokenFault("Expected ')'")
                self.advance()  # Consume ')'
                node = MethodCallNode(node, attr_token, args, kwargs)
                node.line = dot_line
            else:
                # Attribute read: obj.attr
                node = AttributeAccessNode(node, attr_token)
                node.line = dot_line

        return node

    # identifier_expr() disambiguates between a variable access and a function
    # call by peeking at the token after the identifier.
    def identifier_expr(self):
        token = self.current_token
        self.advance()  # Consume the identifier
        if self.current_token.type == TokenType.LPAREN:
            # Function call: identifier(arg, …) or identifier(name: val, …)
            self.advance()  # Consume '('
            args, kwargs = self.parse_call_args()
            if self.current_token.type != TokenType.RPAREN:
                raise UnexpectedTokenFault("Expected ',' or ')'")
            self.advance()  # Consume ')'
            node = CallNode(token, args, kwargs); node.line = token.line
            return node
        else:
            # Plain variable read
            node = VarAccessNode(token); node.line = token.line
            return node

    # lambda_or_anon() parses both forms of anonymous callable:
    #   Short (lambda):  fn(x) => expr          — expr is implicitly returned
    #   Long (anon fn):  fn(x) { body }         — body may contain any statements
    def lambda_or_anon(self):
        line = self.current_token.line
        self.advance()  # Consume 'fn'

        if self.current_token.type != TokenType.LPAREN:
            raise StructureFault("Expected '(' after 'fn'")
        self.advance()  # Consume '('

        params = []
        if self.current_token.type in (TokenType.IDENTIFIER, TokenType.SELF):
            params.append(self.current_token)
            self.advance()
            while self.current_token.type == TokenType.COMMA:
                self.advance()
                if self.current_token.type not in (TokenType.IDENTIFIER, TokenType.SELF):
                    raise UnexpectedTokenFault("Expected parameter name")
                params.append(self.current_token)
                self.advance()

        if self.current_token.type != TokenType.RPAREN:
            raise UnexpectedTokenFault("Expected ')'")
        self.advance()  # Consume ')'

        if self.current_token.type == TokenType.ARROW:
            # Short form: fn(x) => expr
            self.advance()  # Consume '=>'
            expr = self.expr()
            node = LambdaNode(params, expr)
            node.line = line
            return node

        if self.current_token.type == TokenType.LBRACE:
            # Long form: fn(x) { body }
            self.advance()  # Consume '{'
            block = self.statements()
            if self.current_token.type != TokenType.RBRACE:
                raise UnexpectedTokenFault("Expected '}'")
            self.advance()  # Consume '}'
            node = AnonFuncNode(params, block)
            node.line = line
            return node

        raise StructureFault("Expected '=>' or '{' after lambda parameters")

    # _parse_fstring_parts() splits the raw template stored in a FSTRING token
    # into a list of alternating literal strings and expression AST nodes.
    # Example:  "Hello {name}, you have {count} messages"
    #   → ["Hello ", VarAccessNode(name), ", you have ", VarAccessNode(count), " messages"]
    def _parse_fstring_parts(self, token):
        from .lexer import Lexer as _Lexer
        raw = token.value
        parts = []
        i = 0
        while i < len(raw):
            if raw[i] == '{':
                # Find the matching closing brace, tracking depth for nested {}
                depth = 1
                j = i + 1
                while j < len(raw) and depth > 0:
                    if raw[j] == '{':
                        depth += 1
                    elif raw[j] == '}':
                        depth -= 1
                    j += 1
                expr_text = raw[i + 1: j - 1]
                # Sub-parse the expression inside { } using a fresh Lexer+Parser
                sub_tokens = _Lexer(expr_text).get_tokens()
                sub_parser = Parser(sub_tokens)
                parts.append(sub_parser.expr())
                i = j
            else:
                # Collect the literal text up to the next '{' or end of template
                j = i
                while j < len(raw) and raw[j] != '{':
                    j += 1
                if j > i:
                    parts.append(raw[i:j])
                i = j
        node = FStringNode(parts)
        return node

    # list_literal() parses:  [ expr, expr, … ]
    # or a list comprehension: [ expr for var in iterable ]
    #                          [ expr for var in iterable if condition ]
    def list_literal(self):
        line = self.current_token.line
        self.advance()  # Consume '['

        if self.current_token.type == TokenType.RBRACKET:
            self.advance()
            node = ListNode([]); node.line = line
            return node

        first = self.expr()

        # If the next token is 'for', this is a list comprehension
        if self.current_token.type == TokenType.FOR:
            self.advance()  # Consume 'for'
            if self.current_token.type != TokenType.IDENTIFIER:
                raise UnexpectedTokenFault("Expected variable name after 'for' in list comprehension")
            var_token = self.current_token
            self.advance()  # Consume var name
            if self.current_token.type != TokenType.IN:
                raise UnexpectedTokenFault("Expected 'in' after variable in list comprehension")
            self.advance()  # Consume 'in'
            iterable = self.expr()
            condition = None
            if self.current_token.type == TokenType.IF:
                self.advance()  # Consume 'if'
                condition = self.expr()
            if self.current_token.type != TokenType.RBRACKET:
                raise UnexpectedTokenFault("Expected ']' at the end of list comprehension")
            self.advance()  # Consume ']'
            node = ListCompNode(first, var_token, iterable, condition)
            node.line = line
            return node

        # Otherwise it's a regular list literal
        elements = [first]
        while self.current_token.type == TokenType.COMMA:
            self.advance()  # Consume ','
            if self.current_token.type == TokenType.RBRACKET:
                break  # Trailing comma
            elements.append(self.expr())

        if self.current_token.type != TokenType.RBRACKET:
            raise UnexpectedTokenFault("Expected ']' at the end of list")
        self.advance()  # Consume ']'
        node = ListNode(elements); node.line = line
        return node

    # dict_literal() parses:  { key: value, key: value, … }
    # Keys can be any expression, though in practice they will usually be
    # strings or numbers.  A trailing comma before '}' is also permitted.
    def dict_literal(self):
        line = self.current_token.line
        self.advance()  # Consume '{'
        pairs = []
        if self.current_token.type != TokenType.RBRACE:
            key = self.expr()
            if self.current_token.type != TokenType.COLON:
                raise StructureFault("Expected ':' after dictionary key")
            self.advance()  # Consume ':'
            value = self.expr()
            pairs.append((key, value))

            while self.current_token.type == TokenType.COMMA:
                self.advance()  # Consume ','
                if self.current_token.type == TokenType.RBRACE:
                    break  # Trailing comma — stop before '}'
                key = self.expr()
                if self.current_token.type != TokenType.COLON:
                    raise StructureFault("Expected ':' after dictionary key")
                self.advance()  # Consume ':'
                value = self.expr()
                pairs.append((key, value))

        if self.current_token.type != TokenType.RBRACE:
            raise UnexpectedTokenFault("Expected '}' at the end of dictionary")
        self.advance()  # Consume '}'
        node = DictNode(pairs); node.line = line
        return node

    def _is_dict_destructure(self):
        """Scan ahead from LBRACE to check if it's {id, id, ...} = pattern."""
        i = self.pos + 1  # skip '{'
        if i >= len(self.tokens) or self.tokens[i].type != TokenType.IDENTIFIER:
            return False
        i += 1
        while i < len(self.tokens) and self.tokens[i].type == TokenType.COMMA:
            i += 1
            if i >= len(self.tokens) or self.tokens[i].type != TokenType.IDENTIFIER:
                return False
            i += 1
        return (i < len(self.tokens) and self.tokens[i].type == TokenType.RBRACE and
                i + 1 < len(self.tokens) and self.tokens[i + 1].type == TokenType.ASSIGN)

    def dict_destructure_assign(self):
        line = self.current_token.line
        self.advance()  # Consume '{'
        key_tokens = [self.current_token]
        self.advance()  # Consume first identifier
        while self.current_token.type == TokenType.COMMA:
            self.advance()  # Consume ','
            key_tokens.append(self.current_token)
            self.advance()  # Consume identifier
        self.advance()  # Consume '}'
        self.advance()  # Consume '='
        rhs = self.expr()
        node = DictDestructureAssignNode(key_tokens, rhs)
        node.line = line
        return node

    # parse_call_args() parses the argument list inside a function/method call,
    # supporting both positional and named arguments.
    # Named args: identifier: expr   (must come after all positional args)
    # Returns (positional_list, kwargs_dict).
    def parse_call_args(self):
        positional = []
        kwargs = {}
        named_started = False
        while self.current_token.type != TokenType.RPAREN:
            # Detect named arg: IDENTIFIER followed by COLON
            is_named = (
                self.current_token.type == TokenType.IDENTIFIER and
                self.pos + 1 < len(self.tokens) and
                self.tokens[self.pos + 1].type == TokenType.COLON
            )
            if is_named:
                named_started = True
                name = self.current_token.value
                self.advance()  # Consume name
                self.advance()  # Consume ':'
                if name in kwargs:
                    raise StructureFault(f"Duplicate named argument '{name}'")
                kwargs[name] = self.expr()
            else:
                if named_started:
                    raise StructureFault("Positional argument cannot follow a named argument")
                positional.append(self.expr())
            if self.current_token.type == TokenType.COMMA:
                self.advance()  # Consume ','
                if self.current_token.type == TokenType.RPAREN:
                    break  # Trailing comma
            elif self.current_token.type != TokenType.RPAREN:
                raise UnexpectedTokenFault("Expected ',' or ')'")
        return positional, kwargs

    # bin_op() is a reusable helper that implements left-associative binary
    # operators for a given precedence level.
    #
    # Parameters:
    #   func – a method reference that parses the next-higher precedence level
    #           (the operands of the operators being handled here)
    #   ops  – a tuple of TokenType values that are the operators at this level
    #
    # It builds a left-leaning tree:  (((a op b) op c) op d)
    # which is correct for left-associative operators.
    #
    # The ExpressionFault catch around the right-hand operand converts a missing
    # operand into a more descriptive OperatorFault message.
    def bin_op(self, func, ops):
        left = func()
        while self.current_token.type in ops:
            op_token = self.current_token
            self.advance()
            try:
                right = func()
            except ExpressionFault:
                raise OperatorFault(f"Operator '{op_token}' expects a valid expression on the right")
            bin_node = BinOpNode(left, op_token, right)
            bin_node.line = op_token.line
            left = bin_node  # The new node becomes the left operand for the next iteration
        return left
