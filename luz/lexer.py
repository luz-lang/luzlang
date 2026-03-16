import string
from .tokens import TokenType, Token

class Lexer:
    KEYWORDS = {
        'if': TokenType.IF,
        'elif': TokenType.ELIF,
        'else': TokenType.ELSE,
        'while': TokenType.WHILE,
        'for': TokenType.FOR,
        'to': TokenType.TO,
        'true': TokenType.TRUE,
        'false': TokenType.FALSE,
        'and': TokenType.AND,
        'or': TokenType.OR,
        'not': TokenType.NOT,
        'function': TokenType.FUNCTION,
        'return': TokenType.RETURN,
    }

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.current_char = self.text[0] if len(self.text) > 0 else None

    def advance(self):
        self.pos += 1
        self.current_char = self.text[self.pos] if self.pos < len(self.text) else None

    def skip_whitespace(self):
        while self.current_char is not None and self.current_char.isspace():
            self.advance()

    def skip_comment(self):
        while self.current_char is not None and self.current_char != '\n':
            self.advance()
        self.advance()

    def make_number(self):
        num_str = ''
        dot_count = 0
        while self.current_char is not None and (self.current_char.isdigit() or self.current_char == '.'):
            if self.current_char == '.':
                if dot_count == 1: break
                dot_count += 1
            num_str += self.current_char
            self.advance()
        
        return Token(TokenType.NUMBER, float(num_str))

    def make_identifier(self):
        id_str = ''
        while self.current_char is not None and (self.current_char in string.ascii_letters + string.digits + '_'):
            id_str += self.current_char
            self.advance()
        
        token_type = self.KEYWORDS.get(id_str, TokenType.IDENTIFIER)
        return Token(token_type, id_str if token_type == TokenType.IDENTIFIER else None)

    def make_string(self):
        string_val = ''
        self.advance() # Saltar la primera comilla
        
        while self.current_char is not None and self.current_char != '"':
            string_val += self.current_char
            self.advance()
        
        if self.current_char != '"':
            raise Exception("String no cerrado con '\"'")
        
        self.advance() # Saltar la última comilla
        return Token(TokenType.STRING, string_val)

    def make_equals(self):
        self.advance()
        if self.current_char == '=':
            self.advance()
            return Token(TokenType.EE)
        return Token(TokenType.ASSIGN)

    def make_not_equals(self):
        self.advance()
        if self.current_char == '=':
            self.advance()
            return Token(TokenType.NE)
        raise Exception("Esperado '=' después de '!'")

    def make_less_than(self):
        self.advance()
        if self.current_char == '=':
            self.advance()
            return Token(TokenType.LTE)
        return Token(TokenType.LT)

    def make_greater_than(self):
        self.advance()
        if self.current_char == '=':
            self.advance()
            return Token(TokenType.GTE)
        return Token(TokenType.GT)

    def get_tokens(self):
        tokens = []
        while self.current_char is not None:
            if self.current_char.isspace():
                self.skip_whitespace()
            elif self.current_char.isdigit() or self.current_char == '.':
                tokens.append(self.make_number())
            elif self.current_char in string.ascii_letters:
                tokens.append(self.make_identifier())
            elif self.current_char == '#':
                self.skip_comment()
            elif self.current_char == '"':
                tokens.append(self.make_string())
            elif self.current_char == '+':
                tokens.append(Token(TokenType.PLUS))
                self.advance()
            elif self.current_char == '-':
                tokens.append(Token(TokenType.MINUS))
                self.advance()
            elif self.current_char == '*':
                tokens.append(Token(TokenType.MUL))
                self.advance()
            elif self.current_char == '/':
                tokens.append(Token(TokenType.DIV))
                self.advance()
            elif self.current_char == '(':
                tokens.append(Token(TokenType.LPAREN))
                self.advance()
            elif self.current_char == ')':
                tokens.append(Token(TokenType.RPAREN))
                self.advance()
            elif self.current_char == ',':
                tokens.append(Token(TokenType.COMMA))
                self.advance()
            elif self.current_char == ':':
                tokens.append(Token(TokenType.COLON))
                self.advance()
            elif self.current_char == '[':
                tokens.append(Token(TokenType.LBRACKET))
                self.advance()
            elif self.current_char == ']':
                tokens.append(Token(TokenType.RBRACKET))
                self.advance()
            elif self.current_char == '{':
                tokens.append(Token(TokenType.LBRACE))
                self.advance()
            elif self.current_char == '}':
                tokens.append(Token(TokenType.RBRACE))
                self.advance()
            elif self.current_char == '=':
                tokens.append(self.make_equals())
            elif self.current_char == '!':
                tokens.append(self.make_not_equals())
            elif self.current_char == '<':
                tokens.append(self.make_less_than())
            elif self.current_char == '>':
                tokens.append(self.make_greater_than())
            else:
                raise Exception(f"Carácter ilegal: '{self.current_char}'")
        
        tokens.append(Token(TokenType.EOF))
        return tokens
