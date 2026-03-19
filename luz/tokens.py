from enum import Enum, auto

class TokenType(Enum):
    INT = auto()
    FLOAT = auto()
    PLUS = auto()
    MINUS = auto()
    MUL = auto()
    DIV = auto()
    LPAREN = auto()
    RPAREN = auto()
    IDENTIFIER = auto()
    ASSIGN = auto()
    EE = auto()          # ==
    NE = auto()          # !=
    LT = auto()          # <
    GT = auto()          # >
    LTE = auto()         # <=
    GTE = auto()         # >=
    IF = auto()
    ELIF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    TO = auto()
    TRUE = auto()
    FALSE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    FUNCTION = auto()
    RETURN = auto()
    IMPORT = auto()
    ATTEMPT = auto()
    RESCUE = auto()
    ALERT = auto()
    STRING = auto()
    COMMA = auto()       # ,
    COLON = auto()       # :
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]
    LBRACE = auto()      # {
    RBRACE = auto()      # }
    EOF = auto()

class Token:
    def __init__(self, type, value=None):
        self.type = type
        self.value = value

    def __repr__(self):
        if self.value is not None:
            return f"{self.type.name}:{self.value}"
        return f"{self.type.name}"
