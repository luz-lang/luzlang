from .tokens import TokenType

class Interpreter:
    def __init__(self):
        self.symbol_table = {}

    def visit(self, node):
        method_name = f'visit_{type(node).__name__}'
        method = getattr(self, method_name, self.no_visit_method)
        return method(node)

    def no_visit_method(self, node):
        raise Exception(f'No visit_{type(node).__name__} method defined')

    def visit_NumberNode(self, node):
        return node.token.value

    def visit_VarAssignNode(self, node):
        var_name = node.var_name_token.value
        value = self.visit(node.value_node)
        self.symbol_table[var_name] = value
        return value

    def visit_VarAccessNode(self, node):
        var_name = node.token.value
        if var_name not in self.symbol_table:
            raise Exception(f"Variable '{var_name}' no definida")
        return self.symbol_table[var_name]

    def visit_BinOpNode(self, node):
        left = self.visit(node.left_node)
        right = self.visit(node.right_node)

        if node.op_token.type == TokenType.PLUS:
            return left + right
        elif node.op_token.type == TokenType.MINUS:
            return left - right
        elif node.op_token.type == TokenType.MUL:
            return left * right
        elif node.op_token.type == TokenType.DIV:
            if right == 0:
                raise Exception("Error: División por cero")
            return left / right
