"""
OpenM Script Parser - Parses and executes macro scripts with if/else support.

Implements AWK-style syntax:
    if condition then command end
    if condition then commands else commands end
    if condition then commands elseif condition then commands else commands end
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Any, Callable


class TokenType(Enum):
    IF = auto()
    THEN = auto()
    ELSE = auto()
    ELSEIF = auto()
    END = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    EQ = auto()      # ==
    NE = auto()      # !=
    LT = auto()      # <
    GT = auto()      # >
    LE = auto()      # <=
    GE = auto()      # >=
    ASSIGN = auto()  # =
    NUMBER = auto()
    STRING = auto()
    IDENTIFIER = auto()
    COMMAND = auto()
    NEWLINE = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: Any
    line: int
    column: int


@dataclass
class IfBlock:
    """Represents an if/elseif/else block structure."""
    condition: List[Token]
    then_body: List[Any]  # Commands or nested IfBlocks
    elseif_blocks: List[tuple] = None  # List of (condition_tokens, body)
    else_body: List[Any] = None
    
    def __post_init__(self):
        if self.elseif_blocks is None:
            self.elseif_blocks = []


class ScriptLexer:
    """Tokenizer for OpenM script language."""
    
    KEYWORDS = {
        'if': TokenType.IF,
        'then': TokenType.THEN,
        'else': TokenType.ELSE,
        'elseif': TokenType.ELSEIF,
        'end': TokenType.END,
        'and': TokenType.AND,
        'or': TokenType.OR,
        'not': TokenType.NOT,
    }
    
    OPERATORS = {
        '==': TokenType.EQ,
        '!=': TokenType.NE,
        '<=': TokenType.LE,
        '>=': TokenType.GE,
        '<': TokenType.LT,
        '>': TokenType.GT,
        '=': TokenType.ASSIGN,
    }
    
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        
    def error(self, msg: str):
        raise SyntaxError(f"Line {self.line}, col {self.column}: {msg}")
        
    def peek(self, offset: int = 0) -> str:
        pos = self.pos + offset
        if pos >= len(self.text):
            return '\0'
        return self.text[pos]
        
    def advance(self) -> str:
        char = self.peek()
        self.pos += 1
        if char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char
        
    def skip_whitespace(self):
        while self.peek() in ' \t\r':
            self.advance()
            
    def skip_comment(self):
        """Skip comment from # to end of line."""
        if self.peek() == '#':
            while self.peek() not in '\n\0':
                self.advance()
            
    def read_string(self) -> str:
        quote = self.advance()  # ' or "
        result = []
        while self.peek() != quote and self.peek() != '\0':
            if self.peek() == '\\':
                self.advance()
                escape = self.advance()
                if escape == 'n':
                    result.append('\n')
                elif escape == 't':
                    result.append('\t')
                else:
                    result.append(escape)
            else:
                result.append(self.advance())
        if self.peek() == quote:
            self.advance()
        return ''.join(result)
        
    def read_number(self) -> float:
        num_str = []
        while self.peek().isdigit() or self.peek() == '.':
            num_str.append(self.advance())
        return float(''.join(num_str))
        
    def read_identifier(self) -> str:
        ident = []
        while self.peek().isalnum() or self.peek() in '_-.%[]@,:*()$/{}':
            ident.append(self.advance())
        return ''.join(ident)
        
    def read_operator(self) -> str:
        # Check 2-char operators first
        two_char = self.peek() + self.peek(1)
        if two_char in ('==', '!=', '<=', '>='):
            self.advance()
            self.advance()
            return two_char
        # Single char operators
        char = self.peek()
        if char in '<>=':
            return self.advance()
        return ''
        
    def tokenize(self) -> List[Token]:
        while True:
            self.skip_whitespace()
            self.skip_comment()
            char = self.peek()
            line, col = self.line, self.column
            
            if char == '\0':
                self.tokens.append(Token(TokenType.EOF, None, line, col))
                break
            elif char == '\n':
                self.tokens.append(Token(TokenType.NEWLINE, None, line, col))
                self.advance()
            elif char in '"\'':
                self.tokens.append(Token(TokenType.STRING, self.read_string(), line, col))
            elif char.isalpha() or char.isdigit():
                ident = self.read_identifier()
                # Check if it's purely numeric (integer or decimal)
                is_number = ident.isdigit() or (
                    ident.count('.') == 1 and
                    ident.replace('.', '').isdigit() and
                    len(ident) > 1
                )
                if is_number:
                    self.tokens.append(Token(TokenType.NUMBER, float(ident), line, col))
                else:
                    token_type = self.KEYWORDS.get(ident.lower(), TokenType.IDENTIFIER)
                    self.tokens.append(Token(token_type, ident, line, col))
            elif char in '<>=!':
                op = self.read_operator()
                if op:
                    token_type = self.OPERATORS[op]
                    self.tokens.append(Token(token_type, op, line, col))
                else:
                    self.error(f"Unexpected character: {char}")
            else:
                # Treat as command/identifier
                ident = self.read_identifier()
                if ident:
                    self.tokens.append(Token(TokenType.IDENTIFIER, ident, line, col))
                else:
                    self.advance()  # Skip unknown char
                    
        return self.tokens


class ScriptParser:
    """Parser for OpenM scripts with if/else support."""
    
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        
    def peek(self, offset: int = 0) -> Token:
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[pos]
        
    def advance(self) -> Token:
        token = self.peek()
        self.pos += 1
        return token
        
    def expect(self, token_type: TokenType) -> Token:
        token = self.advance()
        if token_type == TokenType.COMMAND:
            # COMMAND is a catch-all for non-keyword identifiers
            if token.type not in (TokenType.IDENTIFIER, TokenType.COMMAND):
                raise SyntaxError(f"Expected command, got {token.type.name}")
            return token
        if token.type != token_type:
            raise SyntaxError(f"Expected {token_type.name}, got {token.type.name} at line {token.line}")
        return token
        
    def parse(self) -> List[Any]:
        """Parse script into list of commands and IfBlocks."""
        statements = []
        while self.peek().type != TokenType.EOF:
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        return statements
        
    def parse_statement(self) -> Optional[Any]:
        """Parse a single statement or block."""
        self.skip_newlines()
        
        token = self.peek()
        if token.type == TokenType.EOF:
            return None
            
        if token.type == TokenType.IF:
            return self.parse_if_block()
        else:
            return self.parse_command()
            
    def skip_newlines(self):
        """Skip newline tokens."""
        while self.peek().type == TokenType.NEWLINE:
            self.advance()
            
    def parse_if_block(self) -> IfBlock:
        """Parse if/elseif/else/end block."""
        self.expect(TokenType.IF)
        
        # Parse condition
        condition = self.parse_condition()
        self.expect(TokenType.THEN)
        
        # Parse then body
        then_body = self.parse_body(stop_tokens={TokenType.ELSE, TokenType.ELSEIF, TokenType.END})
        
        elseif_blocks = []
        else_body = None
        
        # Check for elseif/else (support both `elseif` and `else if` forms)
        while True:
            if self.peek().type == TokenType.ELSEIF:
                self.advance()
                elseif_condition = self.parse_condition()
                self.expect(TokenType.THEN)
                elseif_body = self.parse_body(stop_tokens={TokenType.ELSE, TokenType.ELSEIF, TokenType.END})
                elseif_blocks.append((elseif_condition, elseif_body))
            elif self.peek().type == TokenType.ELSE and (
                self.peek(1).type == TokenType.IF or
                (self.peek(1).type == TokenType.NEWLINE and self.peek(2).type == TokenType.IF)
            ):
                self.advance()
                self.skip_newlines()
                self.expect(TokenType.IF)
                elseif_condition = self.parse_condition()
                self.expect(TokenType.THEN)
                elseif_body = self.parse_body(stop_tokens={TokenType.ELSE, TokenType.ELSEIF, TokenType.END})
                elseif_blocks.append((elseif_condition, elseif_body))
            else:
                break
            
        if self.peek().type == TokenType.ELSE:
            self.advance()
            else_body = self.parse_body(stop_tokens={TokenType.END})
            
        self.expect(TokenType.END)
        
        block = IfBlock(condition=condition, then_body=then_body)
        block.elseif_blocks = elseif_blocks
        block.else_body = else_body
        return block
        
    def parse_condition(self) -> List[Token]:
        """Parse condition expression until 'then'."""
        tokens = []
        while self.peek().type not in (TokenType.THEN, TokenType.EOF):
            tokens.append(self.advance())
        return tokens
        
    def parse_body(self, stop_tokens: set) -> List[Any]:
        """Parse body until one of stop tokens is encountered."""
        body = []
        self.skip_newlines()
        
        while self.peek().type not in stop_tokens and self.peek().type != TokenType.EOF:
            if self.peek().type == TokenType.NEWLINE:
                self.advance()
                continue
            if self.peek().type == TokenType.IF:
                body.append(self.parse_if_block())
            else:
                cmd = self.parse_command()
                if cmd:
                    body.append(cmd)
            self.skip_newlines()
            
        return body
        
    def parse_command(self) -> Optional[dict]:
        """Parse a single command."""
        self.skip_newlines()
        
        token = self.peek()
        if token.type in (TokenType.EOF, TokenType.END, TokenType.ELSE, TokenType.ELSEIF):
            return None
            
        if token.type not in (TokenType.IDENTIFIER, TokenType.COMMAND):
            self.advance()  # Skip
            return None
            
        cmd_name = token.value
        self.advance()
        
        # Collect arguments until newline or control token
        args = []
        while self.peek().type not in (TokenType.NEWLINE, TokenType.EOF, 
                                        TokenType.IF, TokenType.ELSE, TokenType.ELSEIF, TokenType.END):
            arg_token = self.advance()
            if arg_token.type == TokenType.STRING:
                # Re-quote strings so downstream commands preserve them
                val = arg_token.value
                if '"' in val:
                    args.append(f"'{val}'")
                else:
                    args.append(f'"{val}"')
            elif arg_token.type == TokenType.NUMBER:
                args.append(arg_token.value)
            elif arg_token.type == TokenType.IDENTIFIER:
                args.append(arg_token.value)
            else:
                args.append(arg_token.value)
                
        args_str = ' '.join(str(a) for a in args)
        # Remove spurious spaces around punctuation tokens the lexer keeps separate
        args_str = args_str.replace('( ', '(').replace(' )', ')').replace(' ,', ',')
        return {'command': cmd_name, 'args': args_str}


class ExpressionEvaluator:
    """Evaluates conditions in if statements."""
    
    def __init__(self, context: dict = None):
        self.context = context or {}
        
    def evaluate(self, tokens: List[Token]) -> bool:
        """Evaluate a condition expression."""
        if not tokens:
            return False
            
        # Convert tokens to postfix notation and evaluate
        values = []
        ops = []
        
        i = 0
        while i < len(tokens):
            token = tokens[i]
            
            if token.type == TokenType.NUMBER:
                values.append(token.value)
            elif token.type == TokenType.STRING:
                values.append(token.value)
            elif token.type == TokenType.IDENTIFIER:
                # Look up in context or treat as string
                values.append(self.context.get(token.value, token.value))
            elif token.type == TokenType.NOT:
                ops.append('not')
            elif token.type in (TokenType.AND, TokenType.OR):
                while ops and self._precedence(ops[-1]) >= self._precedence(token.value):
                    self._apply_op(values, ops.pop())
                ops.append(token.value.lower())
            elif token.type in (TokenType.EQ, TokenType.NE, TokenType.LT, 
                               TokenType.GT, TokenType.LE, TokenType.GE):
                while ops and self._precedence(ops[-1]) >= self._precedence(token.value):
                    self._apply_op(values, ops.pop())
                ops.append(token.value)
            i += 1
            
        while ops:
            self._apply_op(values, ops.pop())
            
        return bool(values[0]) if values else False
        
    def _precedence(self, op: str) -> int:
        if op in ('and', 'or'):
            return 1
        if op == 'not':
            return 3
        return 2  # Comparison operators
        
    def _apply_op(self, values: List, op: str):
        if op == 'not':
            if values:
                values.append(not values.pop())
        elif op == 'and':
            if len(values) >= 2:
                b, a = values.pop(), values.pop()
                values.append(a and b)
        elif op == 'or':
            if len(values) >= 2:
                b, a = values.pop(), values.pop()
                values.append(a or b)
        elif op in ('==', '!=', '<', '>', '<=', '>='):
            if len(values) >= 2:
                b, a = values.pop(), values.pop()
                # Try numeric comparison if both look like numbers
                a_num = self._try_number(a)
                b_num = self._try_number(b)
                if a_num is not None and b_num is not None:
                    a, b = a_num, b_num
                if op == '==':
                    values.append(a == b)
                elif op == '!=':
                    values.append(a != b)
                elif op == '<':
                    values.append(a < b)
                elif op == '>':
                    values.append(a > b)
                elif op == '<=':
                    values.append(a <= b)
                elif op == '>=':
                    values.append(a >= b)
                    
    def _try_number(self, value) -> float:
        """Try to convert value to number, return None if not possible."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None


def parse_script(text: str) -> List[Any]:
    """Parse OpenM script text into executable AST."""
    lexer = ScriptLexer(text)
    tokens = lexer.tokenize()
    parser = ScriptParser(tokens)
    return parser.parse()


def execute_script(statements: List[Any], executor: Callable, context: dict = None) -> List[str]:
    """Execute parsed script statements.
    
    Args:
        statements: List of commands and IfBlocks from parse_script()
        executor: Function that takes (command_name, args_string) and executes
        context: Variable context for condition evaluation
        
    Returns:
        List of error messages
    """
    errors = []
    evaluator = ExpressionEvaluator(context)
    
    def execute_block(body: List[Any]):
        for stmt in body:
            if isinstance(stmt, IfBlock):
                # Evaluate condition
                condition_result = evaluator.evaluate(stmt.condition)
                
                if condition_result:
                    execute_block(stmt.then_body)
                else:
                    # Check elseif blocks
                    executed = False
                    for elseif_condition, elseif_body in stmt.elseif_blocks:
                        if evaluator.evaluate(elseif_condition):
                            execute_block(elseif_body)
                            executed = True
                            break
                    
                    # Execute else if no match
                    if not executed and stmt.else_body:
                        execute_block(stmt.else_body)
            elif isinstance(stmt, dict):
                # Regular command
                try:
                    executor(stmt['command'], stmt['args'])
                except Exception as e:
                    errors.append(f"Error in {stmt['command']}: {e}")
                    
    execute_block(statements)
    return errors
