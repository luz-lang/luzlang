from .tokens import TokenType

class NumberNode:
    def __init__(self, token):
        self.token = token
    def __repr__(self): return f"{self.token.value}"

class VarAccessNode:
    def __init__(self, token):
        self.token = token
    def __repr__(self): return f"{self.token.value}"

class VarAssignNode:
    def __init__(self, var_name_token, value_node):
        self.var_name_token = var_name_token
        self.value_node = value_node
    def __repr__(self): return f"({self.var_name_token.value} = {self.value_node})"

class BinOpNode:
    def __init__(self, left_node, op_token, right_node):
        self.left_node = left_node
        self.op_token = op_token
        self.right_node = right_node
    def __repr__(self): return f"({self.left_node} {self.op_token.type.name} {self.right_node})"

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.current_token = self.tokens[self.pos]

    def advance(self):
        self.pos += 1
        if self.pos < len(self.tokens):
            self.current_token = self.tokens[self.pos]

    def parse(self):
        return self.statement()

    def statement(self):
        if self.current_token.type == TokenType.IDENTIFIER:
            var_name = self.current_token
            self.advance()
            if self.current_token.type == TokenType.ASSIGN:
                self.advance()
                expr = self.expr()
                return VarAssignNode(var_name, expr)
            else:
                # Si no hay asignación, retrocedemos y tratamos como expresión
                self.pos -= 1
                self.current_token = self.tokens[self.pos]
        
        return self.expr()

    def expr(self):
        return self.bin_op(self.term, (TokenType.PLUS, TokenType.MINUS))

    def term(self):
        return self.bin_op(self.factor, (TokenType.MUL, TokenType.DIV))

    def factor(self):
        token = self.current_token
        if token.type == TokenType.NUMBER:
            self.advance()
            return NumberNode(token)
        elif token.type == TokenType.IDENTIFIER:
            self.advance()
            return VarAccessNode(token)
        elif token.type == TokenType.LPAREN:
            self.advance()
            expr = self.expr()
            if self.current_token.type == TokenType.RPAREN:
                self.advance()
                return expr
        raise Exception("Sintaxis inválida")

    def bin_op(self, func, ops):
        left = func()
        while self.current_token.type in ops:
            op_token = self.current_token
            self.advance()
            right = func()
            left = BinOpNode(left, op_token, right)
        return left
