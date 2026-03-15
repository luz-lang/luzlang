import string
from .tokens import TokenType, Token

class Lexer:
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
        
        return Token(TokenType.IDENTIFIER, id_str)

    def get_tokens(self):
        tokens = []
        while self.current_char is not None:
            if self.current_char.isspace():
                self.skip_whitespace()
            elif self.current_char.isdigit() or self.current_char == '.':
                tokens.append(self.make_number())
            elif self.current_char in string.ascii_letters:
                tokens.append(self.make_identifier())
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
            elif self.current_char == '=':
                tokens.append(Token(TokenType.ASSIGN))
                self.advance()
            else:
                raise Exception(f"Carácter ilegal: '{self.current_char}'")
        
        tokens.append(Token(TokenType.EOF))
        return tokens
