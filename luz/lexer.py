# lexer.py
#
# The Lexer (also called a tokenizer or scanner) is the first stage of the
# Luz interpreter pipeline.  Its job is to convert raw source text into a flat
# list of Token objects that the parser can consume.
#
# Pipeline position:
#   Source text (str) → [Lexer.get_tokens()] → list[Token] → Parser
#
# The Lexer works as a simple state machine:
#   • It maintains a current character pointer (self.pos / self.current_char).
#   • get_tokens() loops over every character, dispatching to a specialised
#     helper method (make_number, make_string, …) when it recognises the start
#     of a multi-character token.
#   • Single-character tokens (operators, punctuation) are produced inline.
#   • Whitespace and comments are silently skipped.
#
# Error handling: when an unrecognised character is encountered, or a string
# literal is malformed, an InvalidTokenFault is raised with the source line
# attached so the user sees a useful error message.

import string
from .tokens import TokenType, Token
from .exceptions import InvalidTokenFault


class Lexer:
    # KEYWORDS maps every reserved word in Luz to its TokenType.
    # When make_identifier() finishes accumulating an alphanumeric sequence it
    # looks the result up here.  If found, a keyword token is returned (with
    # value=None, since the type already encodes all the information).  If not
    # found, a plain IDENTIFIER token carrying the name string is returned.
    KEYWORDS = {
        'if': TokenType.IF,
        'elif': TokenType.ELIF,
        'else': TokenType.ELSE,
        'while': TokenType.WHILE,
        'for': TokenType.FOR,
        'to': TokenType.TO,
        'in': TokenType.IN,
        'true': TokenType.TRUE,
        'false': TokenType.FALSE,
        'null': TokenType.NULL,
        'and': TokenType.AND,
        'or': TokenType.OR,
        'not': TokenType.NOT,
        'function': TokenType.FUNCTION,
        'return': TokenType.RETURN,
        'fn': TokenType.FN,
        'import': TokenType.IMPORT,
        'from': TokenType.FROM,
        'as': TokenType.AS,
        'attempt': TokenType.ATTEMPT,
        'rescue': TokenType.RESCUE,
        'finally': TokenType.FINALLY,
        'alert': TokenType.ALERT,
        'break': TokenType.BREAK,
        'continue': TokenType.CONTINUE,
        'pass': TokenType.PASS,
        'class': TokenType.CLASS,
        'self': TokenType.SELF,
        'extends': TokenType.EXTENDS,
        'switch': TokenType.SWITCH,
        'case': TokenType.CASE,
        'match': TokenType.MATCH,
        'step': TokenType.STEP,
    }

    # ESCAPE_SEQUENCES maps the character after a backslash to the actual
    # character value that should be stored in the string token.  Keeping this
    # as a class-level dict avoids rebuilding it on every string literal and
    # makes it easy to add new sequences in the future.
    ESCAPE_SEQUENCES = {
        'n': '\n',    # newline
        't': '\t',    # horizontal tab
        'r': '\r',    # carriage return
        '\\': '\\',   # literal backslash
        '"': '"',     # double quote (needed to embed quotes inside strings)
    }

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.line = 1  # 1-based line counter, incremented whenever '\n' is consumed
        # Pre-load the first character so every helper can always read self.current_char
        # without bounds-checking.  None signals "end of input".
        self.current_char = self.text[0] if len(self.text) > 0 else None

    # advance() moves the pointer one step forward.
    # Newline tracking happens here rather than in every caller because this is
    # the single choke-point through which every character passes.
    def advance(self):
        if self.current_char == '\n':
            self.line += 1
        self.pos += 1
        self.current_char = self.text[self.pos] if self.pos < len(self.text) else None

    # skip_whitespace() consumes spaces, tabs, and newlines without producing
    # any token.  Luz is not whitespace-sensitive (unlike Python), so indentation
    # has no syntactic meaning.
    def skip_whitespace(self):
        while self.current_char is not None and self.current_char.isspace():
            self.advance()

    # skip_comment() discards everything from '#' to the end of the line.
    # The trailing advance() after the loop consumes the '\n' itself (or is a
    # no-op at EOF), ensuring the line counter is bumped correctly.
    def skip_comment(self):
        while self.current_char is not None and self.current_char != '\n':
            self.advance()
        self.advance()

    # make_number() reads a sequence of digits and at most one decimal point,
    # then returns either an INT or FLOAT token depending on whether a '.' was
    # found.  The line is captured before consumption so the token reports the
    # line where the literal starts, not where it ends.
    def make_number(self):
        num_str = ''
        dot_count = 0
        line = self.line
        while self.current_char is not None and (self.current_char.isdigit() or self.current_char == '.'):
            if self.current_char == '.':
                # A second dot cannot be part of this number literal — stop
                # here so the dot becomes the next token (e.g. for method-call
                # syntax if that is added later).
                if dot_count == 1: break
                dot_count += 1
            num_str += self.current_char
            self.advance()

        if dot_count == 0:
            return Token(TokenType.INT, int(num_str), line)
        else:
            return Token(TokenType.FLOAT, float(num_str), line)

    # make_identifier() reads a run of letters, digits, and underscores.
    # After collection the string is checked against KEYWORDS.  Storing the
    # value only for non-keyword tokens avoids wasting memory on strings for
    # tokens whose type already fully identifies them (e.g. 'if', 'while').
    def make_identifier(self):
        id_str = ''
        line = self.line
        while self.current_char is not None and (self.current_char in string.ascii_letters + string.digits + '_'):
            id_str += self.current_char
            self.advance()

        token_type = self.KEYWORDS.get(id_str, TokenType.IDENTIFIER)
        # IDENTIFIER and SELF tokens carry the name string as their value so
        # the parser can use token.value to look them up in the environment.
        # All other keyword tokens don't need a value — their type is sufficient.
        needs_value = token_type in (TokenType.IDENTIFIER, TokenType.SELF)
        return Token(token_type, id_str if needs_value else None, line)

    # make_string() processes a double-quoted string literal, including backslash
    # escape sequences.  The opening quote has already been identified by
    # get_tokens() but not consumed; this method consumes both delimiters.
    def make_string(self):
        string_val = ''
        line = self.line
        self.advance()  # Consume the opening '"'

        while self.current_char is not None and self.current_char != '"':
            if self.current_char == '\\':
                # Escape sequence: consume the backslash, then inspect the
                # next character to decide what actual character to append.
                self.advance()
                if self.current_char is None:
                    # The source ended immediately after a backslash — the
                    # string was never closed properly.
                    e = InvalidTokenFault("Unexpected end of string after '\\'")
                    e.line = line
                    raise e
                escaped = self.ESCAPE_SEQUENCES.get(self.current_char)
                if escaped is None:
                    # Luz only recognises the sequences listed in the dict.
                    # Anything else (e.g. \q) is an error rather than being
                    # silently passed through, which helps catch typos.
                    e = InvalidTokenFault(f"Unknown escape sequence '\\{self.current_char}'")
                    e.line = line
                    raise e
                string_val += escaped
            else:
                string_val += self.current_char
            self.advance()

        # If we exit the loop because current_char is None (not '"'), the
        # string was never terminated — report an error.
        if self.current_char != '"':
            e = InvalidTokenFault("Unterminated string literal: expected '\"'")
            e.line = line
            raise e

        self.advance()  # Consume the closing '"'
        return Token(TokenType.STRING, string_val, line)

    # make_fstring() collects the raw template content of a $"..." format string.
    # It does NOT parse expressions — that happens in the parser.  The raw
    # content is stored as-is so the parser can split on { } and sub-parse each
    # embedded expression.  Escape sequences outside of { } are resolved here;
    # characters inside { } are kept verbatim so the parser receives valid code.
    def make_fstring(self, line):
        raw = ''
        self.advance()  # Consume opening '"'
        brace_depth = 0
        while self.current_char is not None:
            if brace_depth == 0 and self.current_char == '"':
                break  # Closing quote reached outside any expression
            if self.current_char == '{':
                brace_depth += 1
                raw += self.current_char
                self.advance()
            elif self.current_char == '}':
                brace_depth -= 1
                raw += self.current_char
                self.advance()
            elif self.current_char == '\\' and brace_depth == 0:
                # Escape sequences only apply outside { }
                self.advance()
                if self.current_char is None:
                    e = InvalidTokenFault("Unexpected end of format string after '\\'")
                    e.line = line
                    raise e
                escaped = self.ESCAPE_SEQUENCES.get(self.current_char)
                if escaped is None:
                    e = InvalidTokenFault(f"Unknown escape sequence '\\{self.current_char}'")
                    e.line = line
                    raise e
                raw += escaped
                self.advance()
            else:
                raw += self.current_char
                self.advance()

        if self.current_char != '"':
            e = InvalidTokenFault("Unterminated format string")
            e.line = line
            raise e
        self.advance()  # Consume closing '"'
        return Token(TokenType.FSTRING, raw, line)

    # make_slash() handles the ambiguity between '/' (division) and '//'
    # (integer division).  After consuming the first '/', it peeks at the next
    # character to decide which token to emit.
    def make_slash(self):
        line = self.line
        self.advance()  # Consume the first '/'
        if self.current_char == '/':
            self.advance()  # Consume the second '/'
            return Token(TokenType.IDIV, None, line)
        if self.current_char == '=':
            self.advance()
            return Token(TokenType.DIV_ASSIGN, None, line)
        return Token(TokenType.DIV, None, line)

    # make_star() handles '*' (multiplication) vs '**' (exponentiation).
    def make_star(self):
        line = self.line
        self.advance()  # Consume the first '*'
        if self.current_char == '*':
            self.advance()  # Consume the second '*'
            if self.current_char == '=':
                self.advance()
                return Token(TokenType.POW_ASSIGN, None, line)
            return Token(TokenType.POW, None, line)
        if self.current_char == '=':
            self.advance()
            return Token(TokenType.MUL_ASSIGN, None, line)
        return Token(TokenType.MUL, None, line)

    # make_equals() handles '=' (assignment), '==' (equality), and '=>' (arrow).
    def make_equals(self):
        line = self.line
        self.advance()  # Consume the first '='
        if self.current_char == '=':
            self.advance()  # Consume the second '='
            return Token(TokenType.EE, None, line)
        if self.current_char == '>':
            self.advance()  # Consume '>'
            return Token(TokenType.ARROW, None, line)
        return Token(TokenType.ASSIGN, None, line)

    # make_not_equals() handles '!=' only.  A bare '!' is not a valid token in
    # Luz (logical NOT is the keyword 'not'), so failing to find '=' after '!'
    # is always a hard error.
    def make_not_equals(self):
        line = self.line
        self.advance()  # Consume '!'
        if self.current_char == '=':
            self.advance()  # Consume '='
            return Token(TokenType.NE, None, line)
        e = InvalidTokenFault("Expected '=' after '!'")
        e.line = line
        raise e

    # make_less_than() handles '<' (less-than) vs '<=' (less-than-or-equal).
    def make_less_than(self):
        line = self.line
        self.advance()  # Consume '<'
        if self.current_char == '=':
            self.advance()  # Consume '='
            return Token(TokenType.LTE, None, line)
        return Token(TokenType.LT, None, line)

    # make_greater_than() handles '>' vs '>='.
    def make_greater_than(self):
        line = self.line
        self.advance()  # Consume '>'
        if self.current_char == '=':
            self.advance()  # Consume '='
            return Token(TokenType.GTE, None, line)
        return Token(TokenType.GT, None, line)

    # get_tokens() is the main entry point.  It loops until end-of-input,
    # dispatching to the appropriate helper for each character category.
    # After the loop it appends a synthetic EOF token so the parser always has
    # a well-defined stopping condition without needing bounds checks.
    def get_tokens(self):
        tokens = []
        while self.current_char is not None:
            if self.current_char.isspace():
                self.skip_whitespace()

            # Numbers start with a digit, or with '.' only when followed by a digit
            # (e.g. .5 == 0.5).  A bare '.' not followed by a digit is a DOT token
            # for attribute access, handled further down.
            elif self.current_char.isdigit() or (
                self.current_char == '.' and
                self.pos + 1 < len(self.text) and
                self.text[self.pos + 1].isdigit()
            ):
                tokens.append(self.make_number())

            # Identifiers and keywords start with a letter or underscore.
            elif self.current_char in string.ascii_letters or self.current_char == '_':
                tokens.append(self.make_identifier())

            elif self.current_char == '#':
                self.skip_comment()

            elif self.current_char == '$':
                line = self.line
                self.advance()  # Consume '$'
                if self.current_char != '"':
                    e = InvalidTokenFault("Expected '\"' after '$' for format string")
                    e.line = line
                    raise e
                tokens.append(self.make_fstring(line))

            elif self.current_char == '"':
                tokens.append(self.make_string())

            # Single-character operators are produced inline — no helper needed.
            elif self.current_char == '+':
                line = self.line
                self.advance()
                if self.current_char == '=':
                    self.advance()
                    tokens.append(Token(TokenType.PLUS_ASSIGN, None, line))
                else:
                    tokens.append(Token(TokenType.PLUS, None, line))
            elif self.current_char == '-':
                line = self.line
                self.advance()
                if self.current_char == '=':
                    self.advance()
                    tokens.append(Token(TokenType.MINUS_ASSIGN, None, line))
                else:
                    tokens.append(Token(TokenType.MINUS, None, line))

            # Multi-character operators need lookahead — delegate to helpers.
            elif self.current_char == '*':
                tokens.append(self.make_star())
            elif self.current_char == '%':
                line = self.line
                self.advance()
                if self.current_char == '=':
                    self.advance()
                    tokens.append(Token(TokenType.MOD_ASSIGN, None, line))
                else:
                    tokens.append(Token(TokenType.MOD, None, line))
            elif self.current_char == '/':
                tokens.append(self.make_slash())

            # Grouping / collection delimiters
            elif self.current_char == '(':
                tokens.append(Token(TokenType.LPAREN, None, self.line))
                self.advance()
            elif self.current_char == ')':
                tokens.append(Token(TokenType.RPAREN, None, self.line))
                self.advance()
            elif self.current_char == ',':
                tokens.append(Token(TokenType.COMMA, None, self.line))
                self.advance()
            elif self.current_char == ':':
                tokens.append(Token(TokenType.COLON, None, self.line))
                self.advance()
            elif self.current_char == '[':
                tokens.append(Token(TokenType.LBRACKET, None, self.line))
                self.advance()
            elif self.current_char == ']':
                tokens.append(Token(TokenType.RBRACKET, None, self.line))
                self.advance()
            elif self.current_char == '{':
                tokens.append(Token(TokenType.LBRACE, None, self.line))
                self.advance()
            elif self.current_char == '}':
                tokens.append(Token(TokenType.RBRACE, None, self.line))
                self.advance()

            # Comparison and assignment operators (all need lookahead)
            elif self.current_char == '=':
                tokens.append(self.make_equals())
            elif self.current_char == '!':
                tokens.append(self.make_not_equals())
            elif self.current_char == '<':
                tokens.append(self.make_less_than())
            elif self.current_char == '>':
                tokens.append(self.make_greater_than())
            elif self.current_char == ".":
                line = self.line
                # Check for ellipsis `...` before falling back to DOT
                if self.pos + 2 < len(self.text) and self.text[self.pos + 1] == '.' and self.text[self.pos + 2] == '.':
                    self.advance(); self.advance(); self.advance()
                    tokens.append(Token(TokenType.ELLIPSIS, None, line))
                else:
                    tokens.append(Token(TokenType.DOT, None, line))
                    self.advance()

            elif self.current_char == '?':
                line = self.line
                self.advance()
                if self.current_char == '?':
                    self.advance()
                    tokens.append(Token(TokenType.NULL_COALESCE, None, line))
                else:
                    e = InvalidTokenFault("Expected '?' after '?' for null-coalescing operator '??'")
                    e.line = line
                    raise e

            else:
                # No rule matched — the character is not part of the Luz alphabet.
                e = InvalidTokenFault(f"Illegal character: '{self.current_char}'")
                e.line = self.line
                raise e

        # The EOF sentinel lets the parser detect the end of input without
        # ever indexing past the end of the token list.
        tokens.append(Token(TokenType.EOF))
        return tokens
