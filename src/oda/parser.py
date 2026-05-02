"""Recursive-descent parser for OdaLanguage."""
from __future__ import annotations
from .tokens import Token, TokenType, TYPE_TOKENS
from .errors import ParserError
from . import ast_nodes as ast


class Parser:
    def __init__(self, tokens: list[Token], filename: str = "<source>"):
        self.tokens = tokens
        self.filename = filename
        self.pos = 0

    # ── helpers ──────────────────────────────────────────────
    def _cur(self) -> Token:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else self.tokens[-1]

    def _peek(self, offset=1) -> Token:
        i = self.pos + offset
        return self.tokens[i] if i < len(self.tokens) else self.tokens[-1]

    def _at(self, *types: TokenType) -> bool:
        return self._cur().type in types

    def _advance(self) -> Token:
        t = self._cur()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return t

    def _expect(self, ttype: TokenType, msg: str = "") -> Token:
        if self._cur().type != ttype:
            t = self._cur()
            raise ParserError(msg or f"Expected {ttype.name}, got {t.type.name} ({t.value!r})",
                              t.line, t.column, self.filename)
        return self._advance()

    def _skip_newlines(self):
        while self._at(TokenType.NEWLINE):
            self._advance()

    def _consume_terminator(self):
        if self._at(TokenType.NEWLINE, TokenType.SEMICOLON):
            self._advance()
        # also OK at EOF or before '}'

    # ── public entry ─────────────────────────────────────────
    def parse(self) -> ast.Program:
        prog = ast.Program(line=1, column=1)
        self._skip_newlines()
        while not self._at(TokenType.EOF):
            stmt = self._statement()
            if stmt is not None:
                prog.statements.append(stmt)
            self._skip_newlines()
        return prog

    # ── statements ───────────────────────────────────────────
    def _statement(self):
        self._skip_newlines()
        t = self._cur()

        if t.type == TokenType.STAY:
            return self._var_decl_stay()
        if t.type in TYPE_TOKENS or (t.type == TokenType.IDENTIFIER and self._peek().type == TokenType.IDENTIFIER):
            return self._var_or_expr()
        if t.type == TokenType.FUNC:
            return self._func_decl()
        if t.type == TokenType.CLASS:
            return self._class_decl()
        if t.type == TokenType.IF:
            return self._if_stmt()
        if t.type == TokenType.WHILE:
            return self._while_stmt()
        if t.type == TokenType.FOR:
            return self._for_stmt()
        if t.type == TokenType.RETURN:
            return self._return_stmt()
        if t.type == TokenType.BREAK:
            self._advance(); self._consume_terminator()
            return ast.BreakStatement(line=t.line, column=t.column)
        if t.type == TokenType.CONTINUE:
            self._advance(); self._consume_terminator()
            return ast.ContinueStatement(line=t.line, column=t.column)
        if t.type == TokenType.GUARD:
            return self._guard_stmt()
        if t.type == TokenType.MATCH:
            return self._match_stmt()
        if t.type in (TokenType.IMPORT, TokenType.FROM):
            return self._import_stmt()
        if t.type == TokenType.CONSTRUCT:
            return self._construct_block()
        if t.type == TokenType.DESTRUCT:
            return self._destruct_block()

        return self._expr_statement()

    # ── variable declaration ─────────────────────────────────
    def _var_decl_stay(self):
        t = self._advance()  # consume 'stay'
        ta = self._type_annotation()
        name = self._expect(TokenType.IDENTIFIER, "Expected variable name").value
        init = None
        if self._at(TokenType.ASSIGN):
            self._advance()
            init = self._expression()
        self._consume_terminator()
        return ast.VarDeclaration(line=t.line, column=t.column,
                                  type_ann=ta, name=name, is_immutable=True, initializer=init)

    def _var_or_expr(self):
        """Disambiguate 'int x = ...' vs expression statement."""
        t = self._cur()
        if t.type in TYPE_TOKENS:
            return self._var_decl()
        # Could be ClassName identifier (constructor call pattern handled elsewhere)
        if t.type == TokenType.IDENTIFIER and self._peek().type == TokenType.IDENTIFIER:
            return self._var_decl_classtype()
        return self._expr_statement()

    def _var_decl(self):
        t = self._cur()
        ta = self._type_annotation()
        name = self._expect(TokenType.IDENTIFIER, "Expected variable name").value
        init = None
        if self._at(TokenType.ASSIGN):
            self._advance()
            init = self._expression()
        self._consume_terminator()
        return ast.VarDeclaration(line=t.line, column=t.column,
                                  type_ann=ta, name=name, initializer=init)

    def _var_decl_classtype(self):
        t = self._cur()
        class_name = self._advance().value
        ta = ast.TypeAnnotation(base_type=class_name, line=t.line, column=t.column)
        if self._at(TokenType.QUESTION):
            self._advance(); ta.is_nullable = True
        name = self._expect(TokenType.IDENTIFIER, "Expected variable name").value
        init = None
        if self._at(TokenType.ASSIGN):
            self._advance()
            init = self._expression()
        self._consume_terminator()
        return ast.VarDeclaration(line=t.line, column=t.column,
                                  type_ann=ta, name=name, initializer=init)

    def _type_annotation(self) -> ast.TypeAnnotation:
        t = self._cur()
        if t.type in TYPE_TOKENS:
            base = self._advance().value
        elif t.type == TokenType.IDENTIFIER:
            base = self._advance().value
        else:
            raise ParserError(f"Expected type, got {t.value!r}", t.line, t.column, self.filename)

        ta = ast.TypeAnnotation(base_type=base, line=t.line, column=t.column)

        if self._at(TokenType.QUESTION):
            self._advance(); ta.is_nullable = True
        elif self._at(TokenType.NOT):
            self._advance(); ta.is_result = True

        while self._at(TokenType.LBRACKET):
            self._advance()
            ta.is_array = True
            ta.array_depth += 1
            if self._at(TokenType.INTEGER):
                sz = int(self._advance().value)
                if ta.array_depth == 1:
                    ta.array_size = sz
                ta.fixed_sizes.append(sz)
            self._expect(TokenType.RBRACKET, "Expected ']'")
        return ta

    # ── function declaration ─────────────────────────────────
    def _func_decl(self) -> ast.FuncDeclaration:
        t = self._advance()  # 'func'
        name = self._expect(TokenType.IDENTIFIER, "Expected function name").value
        self._expect(TokenType.LPAREN)
        params = self._param_list()
        self._expect(TokenType.RPAREN)
        ret = None
        if self._at(TokenType.ARROW):
            self._advance()
            ret = self._type_annotation()
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        body = self._block()
        self._expect(TokenType.RBRACE)
        return ast.FuncDeclaration(line=t.line, column=t.column,
                                   name=name, params=params, return_type=ret, body=body)

    def _param_list(self) -> list[ast.Parameter]:
        params = []
        while not self._at(TokenType.RPAREN, TokenType.EOF):
            is_ref = False
            if self._at(TokenType.REF):
                self._advance(); is_ref = True
            ta = self._type_annotation()
            name = self._expect(TokenType.IDENTIFIER).value
            params.append(ast.Parameter(type_ann=ta, name=name, is_ref=is_ref,
                                        line=ta.line, column=ta.column))
            if not self._at(TokenType.RPAREN):
                self._expect(TokenType.COMMA)
        return params

    # ── class declaration ────────────────────────────────────
    def _class_decl(self) -> ast.ClassDeclaration:
        t = self._advance()  # 'class'
        name = self._expect(TokenType.IDENTIFIER).value
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        cls = ast.ClassDeclaration(line=t.line, column=t.column, name=name)
        self._skip_newlines()
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            cur = self._cur()
            if cur.type == TokenType.FUNC:
                cls.methods.append(self._func_decl())
            elif cur.type == TokenType.CONSTRUCT:
                cls.constructor = self._construct_block()
            elif cur.type == TokenType.DESTRUCT:
                cls.destructor = self._destruct_block()
            elif cur.type in TYPE_TOKENS:
                cls.fields.append(self._var_decl())
            else:
                self._advance()  # skip unknown
            self._skip_newlines()
        self._expect(TokenType.RBRACE)
        return cls

    def _construct_block(self) -> ast.FuncDeclaration:
        t = self._advance()  # 'construct'
        self._expect(TokenType.LPAREN)
        params = self._param_list()
        self._expect(TokenType.RPAREN)
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        body = self._block()
        self._expect(TokenType.RBRACE)
        return ast.FuncDeclaration(line=t.line, column=t.column,
                                   name="construct", params=params, body=body)

    def _destruct_block(self) -> ast.FuncDeclaration:
        t = self._advance()  # 'destruct'
        self._expect(TokenType.LPAREN)
        self._expect(TokenType.RPAREN)
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        body = self._block()
        self._expect(TokenType.RBRACE)
        return ast.FuncDeclaration(line=t.line, column=t.column,
                                   name="destruct", params=[], body=body)

    # ── control flow ─────────────────────────────────────────
    def _if_stmt(self) -> ast.IfStatement:
        t = self._advance()  # 'if'
        self._expect(TokenType.LPAREN)
        cond = self._expression()
        self._expect(TokenType.RPAREN)
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        body = self._block()
        self._expect(TokenType.RBRACE)
        elifs = []
        else_body = []
        self._skip_newlines()
        while self._at(TokenType.ELSE):
            self._advance()
            if self._at(TokenType.IF):
                self._advance()
                self._expect(TokenType.LPAREN)
                ec = self._expression()
                self._expect(TokenType.RPAREN)
                self._skip_newlines()
                self._expect(TokenType.LBRACE)
                eb = self._block()
                self._expect(TokenType.RBRACE)
                elifs.append((ec, eb))
                self._skip_newlines()
            else:
                self._skip_newlines()
                self._expect(TokenType.LBRACE)
                else_body = self._block()
                self._expect(TokenType.RBRACE)
                break
        return ast.IfStatement(line=t.line, column=t.column,
                               condition=cond, body=body,
                               elif_branches=elifs, else_body=else_body)

    def _while_stmt(self) -> ast.WhileStatement:
        t = self._advance()
        self._expect(TokenType.LPAREN)
        cond = self._expression()
        self._expect(TokenType.RPAREN)
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        body = self._block()
        self._expect(TokenType.RBRACE)
        return ast.WhileStatement(line=t.line, column=t.column, condition=cond, body=body)

    def _for_stmt(self):
        t = self._advance()  # 'for'
        
        self._skip_newlines()
        
        # 1. Infinite loop: for { ... }
        if self._at(TokenType.LBRACE):
            self._advance()
            body = self._block()
            self._expect(TokenType.RBRACE)
            return ast.WhileStatement(line=t.line, column=t.column, 
                                      condition=ast.BoolLiteral(line=t.line, column=t.column, value=True), 
                                      body=body)
                                      
        self._expect(TokenType.LPAREN)
        
        # Detect range-based, collection-based, or while-like loop
        is_for_in = False
        has_semicolon = False
        
        p = 0
        while True:
            pt = self._peek(p)
            if pt.type == TokenType.EOF or pt.type == TokenType.RPAREN:
                break
            if pt.type == TokenType.SEMICOLON:
                has_semicolon = True
                break
            p += 1

        p = 0
        if self._peek(p).type in TYPE_TOKENS or self._peek(p).type == TokenType.IDENTIFIER:
            p += 1
            while self._peek(p).type == TokenType.LBRACKET:
                p += 1
                if self._peek(p).type == TokenType.INTEGER: p += 1
                if self._peek(p).type == TokenType.RBRACKET: p += 1
            if self._peek(p).type == TokenType.IDENTIFIER and self._peek(p+1).type == TokenType.IN:
                is_for_in = True
        
        if is_for_in:
            return self._for_range(t)
            
        # 2. While-like loop: for (expr) { ... }
        if not has_semicolon:
            cond = self._expression()
            self._expect(TokenType.RPAREN)
            self._skip_newlines()
            self._expect(TokenType.LBRACE)
            body = self._block()
            self._expect(TokenType.RBRACE)
            return ast.WhileStatement(line=t.line, column=t.column, condition=cond, body=body)

        # 3. C-style for
        init = None
        if not self._at(TokenType.SEMICOLON):
            if self._cur().type in TYPE_TOKENS:
                init = self._var_decl_inline()
            else:
                init = self._expression()
        self._expect(TokenType.SEMICOLON)
        cond = None
        if not self._at(TokenType.SEMICOLON):
            cond = self._expression()
        self._expect(TokenType.SEMICOLON)
        update = None
        if not self._at(TokenType.RPAREN):
            update = self._expression()
        self._expect(TokenType.RPAREN)
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        body = self._block()
        self._expect(TokenType.RBRACE)
        return ast.ForStatement(line=t.line, column=t.column,
                                init=init, condition=cond, update=update, body=body)

    def _for_range(self, t: Token):
        vt = self._type_annotation()
        vn = self._expect(TokenType.IDENTIFIER).value
        self._expect(TokenType.IN, "Expected 'in'")
        expr = self._expression()
        
        if self._at(TokenType.RANGE, TokenType.RANGE_INCLUSIVE):
            is_inclusive = self._at(TokenType.RANGE_INCLUSIVE)
            self._advance()
            end = self._expression()
            
            step = None
            if self._at(TokenType.STEP):
                self._advance()
                step = self._expression()
            
            self._expect(TokenType.RPAREN)
            self._skip_newlines()
            self._expect(TokenType.LBRACE)
            body = self._block()
            self._expect(TokenType.RBRACE)
            return ast.ForRangeStatement(line=t.line, column=t.column,
                                         var_type=vt, var_name=vn,
                                         start=expr, end=end, 
                                         is_inclusive=is_inclusive,
                                         step=step, body=body)
        
        is_reversed = False
        if self._at(TokenType.REVERSED):
            self._advance()
            is_reversed = True
            
        step = None
        if self._at(TokenType.STEP):
            self._advance()
            step = self._expression()
        
        self._expect(TokenType.RPAREN)
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        body = self._block()
        self._expect(TokenType.RBRACE)
        return ast.ForInStatement(line=t.line, column=t.column,
                                   var_type=vt, var_name=vn,
                                   iterable=expr, is_reversed=is_reversed,
                                   step=step, body=body)

    def _var_decl_inline(self):
        t = self._cur()
        ta = self._type_annotation()
        name = self._expect(TokenType.IDENTIFIER).value
        init = None
        if self._at(TokenType.ASSIGN):
            self._advance()
            init = self._expression()
        return ast.VarDeclaration(line=t.line, column=t.column,
                                  type_ann=ta, name=name, initializer=init)

    def _return_stmt(self):
        t = self._advance()
        val = None
        if not self._at(TokenType.NEWLINE, TokenType.SEMICOLON, TokenType.RBRACE, TokenType.EOF):
            val = self._expression()
        self._consume_terminator()
        return ast.ReturnStatement(line=t.line, column=t.column, value=val)

    def _guard_stmt(self):
        t = self._advance()  # 'guard'
        ta = self._type_annotation()
        name = self._expect(TokenType.IDENTIFIER).value
        self._expect(TokenType.ASSIGN)
        expr = self._expression()
        self._expect(TokenType.ELSE, "Expected 'else' after guard expression")
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        cases = []
        self._skip_newlines()
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            case_tok = self._expect(TokenType.WHEN, "Expected 'when' in guard else block")
            self._expect(TokenType.LPAREN)
            err_name_parts = [self._expect(TokenType.IDENTIFIER).value]
            while self._at(TokenType.DOT):
                self._advance()
                err_name_parts.append(self._expect(TokenType.IDENTIFIER).value)
            err_name = ".".join(err_name_parts)
            self._expect(TokenType.RPAREN)
            self._skip_newlines()
            self._expect(TokenType.LBRACE)
            cbody = self._block()
            self._expect(TokenType.RBRACE)
            cases.append(ast.WhenCase(line=case_tok.line, column=case_tok.column,
                                      error_type=err_name, body=cbody))
            self._skip_newlines()
        self._expect(TokenType.RBRACE)
        return ast.GuardStatement(line=t.line, column=t.column,
                                  var_type=ta, var_name=name, expr=expr, cases=cases)

    def _match_stmt(self):
        t = self._advance()  # 'match'
        self._expect(TokenType.LPAREN)
        expr = self._expression()
        self._expect(TokenType.RPAREN)
        self._skip_newlines()
        self._expect(TokenType.LBRACE)
        arms = []
        self._skip_newlines()
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            pat = None
            if self._at(TokenType.IDENTIFIER) and self._cur().value == "_":
                self._advance()  # wildcard
            else:
                pat = self._expression()
            self._skip_newlines()
            self._expect(TokenType.LBRACE)
            abody = self._block()
            self._expect(TokenType.RBRACE)
            arms.append(ast.MatchArm(line=t.line, column=t.column, pattern=pat, body=abody))
            self._skip_newlines()
        self._expect(TokenType.RBRACE)
        return ast.MatchStatement(line=t.line, column=t.column, expr=expr, arms=arms)

    def _import_stmt(self):
        t = self._cur()
        if t.type == TokenType.FROM:
            self._advance()
            path = self._dotted_name()
            self._expect(TokenType.IMPORT)
            names = [self._expect(TokenType.IDENTIFIER).value]
            while self._at(TokenType.COMMA):
                self._advance()
                names.append(self._expect(TokenType.IDENTIFIER).value)
            self._consume_terminator()
            return ast.ImportStatement(line=t.line, column=t.column,
                                       module_path=path, names=names)
        self._advance()  # 'import'
        path = self._dotted_name()
        alias = None
        if self._at(TokenType.AS):
            self._advance()
            alias = self._expect(TokenType.IDENTIFIER).value
        self._consume_terminator()
        return ast.ImportStatement(line=t.line, column=t.column,
                                   module_path=path, alias=alias)

    def _dotted_name(self) -> str:
        parts = [self._expect(TokenType.IDENTIFIER).value]
        while self._at(TokenType.DOT):
            self._advance()
            parts.append(self._expect(TokenType.IDENTIFIER).value)
        return ".".join(parts)

    # ── block (list of statements) ───────────────────────────
    def _block(self) -> list:
        stmts = []
        self._skip_newlines()
        while not self._at(TokenType.RBRACE, TokenType.EOF):
            s = self._statement()
            if s is not None:
                stmts.append(s)
            self._skip_newlines()
        return stmts

    # ── expression statement ─────────────────────────────────
    def _expr_statement(self):
        t = self._cur()
        expr = self._expression()
        self._consume_terminator()
        return ast.ExpressionStatement(line=t.line, column=t.column, expr=expr)

    # ── expressions (precedence climbing) ────────────────────
    def _expression(self):
        return self._assignment()

    def _assignment(self):
        left = self._null_coalesce()
        if self._at(TokenType.ASSIGN, TokenType.PLUS_ASSIGN, TokenType.MINUS_ASSIGN,
                    TokenType.STAR_ASSIGN, TokenType.SLASH_ASSIGN):
            op = self._advance().value
            right = self._assignment()
            return ast.AssignExpr(line=left.line, column=left.column,
                                  target=left, op=op, value=right)
        return left

    def _null_coalesce(self):
        left = self._logic_or()
        while self._at(TokenType.NULLISH):
            self._advance()
            right = self._logic_or()
            left = ast.BinaryExpr(line=left.line, column=left.column,
                                   left=left, op="??", right=right)
        return left

    def _logic_or(self):
        left = self._logic_and()
        while self._at(TokenType.OR):
            self._advance()
            right = self._logic_and()
            left = ast.BinaryExpr(line=left.line, column=left.column,
                                   left=left, op="||", right=right)
        return left

    def _logic_and(self):
        left = self._equality()
        while self._at(TokenType.AND):
            self._advance()
            right = self._equality()
            left = ast.BinaryExpr(line=left.line, column=left.column,
                                   left=left, op="&&", right=right)
        return left

    def _equality(self):
        left = self._comparison()
        while self._at(TokenType.EQ, TokenType.NEQ):
            op = self._advance().value
            right = self._comparison()
            left = ast.BinaryExpr(line=left.line, column=left.column,
                                   left=left, op=op, right=right)
        return left

    def _comparison(self):
        left = self._addition()
        while self._at(TokenType.LT, TokenType.GT, TokenType.LTE, TokenType.GTE):
            op = self._advance().value
            right = self._addition()
            left = ast.BinaryExpr(line=left.line, column=left.column,
                                   left=left, op=op, right=right)
        return left

    def _addition(self):
        left = self._multiplication()
        while self._at(TokenType.PLUS, TokenType.MINUS):
            op = self._advance().value
            right = self._multiplication()
            left = ast.BinaryExpr(line=left.line, column=left.column,
                                   left=left, op=op, right=right)
        return left

    def _multiplication(self):
        left = self._unary()
        while self._at(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self._advance().value
            right = self._unary()
            left = ast.BinaryExpr(line=left.line, column=left.column,
                                   left=left, op=op, right=right)
        return left

    def _unary(self):
        if self._at(TokenType.NOT):
            t = self._advance()
            return ast.UnaryExpr(line=t.line, column=t.column, op="!", operand=self._unary())
        if self._at(TokenType.MINUS):
            t = self._advance()
            return ast.UnaryExpr(line=t.line, column=t.column, op="-", operand=self._unary())
        return self._postfix()

    def _postfix(self):
        node = self._primary()
        while True:
            if self._at(TokenType.DOT):
                self._advance()
                member = self._expect(TokenType.IDENTIFIER).value
                node = ast.MemberAccess(line=node.line, column=node.column,
                                         obj=node, member=member)
            elif self._at(TokenType.LPAREN):
                self._advance()
                args, ref_flags = self._arg_list()
                self._expect(TokenType.RPAREN)
                node = ast.CallExpr(line=node.line, column=node.column,
                                     callee=node, args=args, ref_flags=ref_flags)
            elif self._at(TokenType.LBRACKET):
                self._advance()
                idx = self._expression()
                self._expect(TokenType.RBRACKET)
                node = ast.IndexAccess(line=node.line, column=node.column,
                                        obj=node, index=idx)
            else:
                break
        return node

    def _arg_list(self) -> tuple[list, list[bool]]:
        args, refs = [], []
        while not self._at(TokenType.RPAREN, TokenType.EOF):
            is_ref = False
            if self._at(TokenType.REF):
                self._advance(); is_ref = True
            args.append(self._expression())
            refs.append(is_ref)
            if not self._at(TokenType.RPAREN):
                self._expect(TokenType.COMMA)
        return args, refs

    def _primary(self):
        t = self._cur()

        if t.type == TokenType.INTEGER:
            self._advance()
            return ast.IntegerLiteral(line=t.line, column=t.column, value=int(t.value))

        if t.type == TokenType.FLOAT_LIT:
            self._advance()
            return ast.FloatLiteral(line=t.line, column=t.column, value=float(t.value))

        if t.type == TokenType.STRING_LIT:
            self._advance()
            # Check for interpolation {…}
            if "{" in t.value:
                return self._parse_interpolated(t)
            return ast.StringLiteral(line=t.line, column=t.column, value=t.value)

        if t.type == TokenType.CHAR_LIT:
            self._advance()
            return ast.CharLiteral(line=t.line, column=t.column, value=t.value)

        if t.type == TokenType.TRUE:
            self._advance()
            return ast.BoolLiteral(line=t.line, column=t.column, value=True)

        if t.type == TokenType.FALSE:
            self._advance()
            return ast.BoolLiteral(line=t.line, column=t.column, value=False)

        if t.type == TokenType.NULL:
            self._advance()
            return ast.NullLiteral(line=t.line, column=t.column)

        if t.type == TokenType.IDENTIFIER:
            self._advance()
            return ast.Identifier(line=t.line, column=t.column, name=t.value)

        if t.type == TokenType.LPAREN:
            self._advance()
            expr = self._expression()
            self._expect(TokenType.RPAREN)
            return expr

        if t.type == TokenType.LBRACKET:
            self._advance()
            elements = []
            if not self._at(TokenType.RBRACKET):
                elements.append(self._expression())
                while self._at(TokenType.COMMA):
                    self._advance()
                    elements.append(self._expression())
            self._expect(TokenType.RBRACKET, "Expected ']' after array elements")
            return ast.ArrayLiteral(line=t.line, column=t.column, elements=elements)

        if t.type == TokenType.NEW:
            self._advance()
            if self._cur().type in TYPE_TOKENS or self._cur().type == TokenType.IDENTIFIER:
                base = self._advance().value
            else:
                raise ParserError(f"Expected type after 'new', got {self._cur().value!r}", t.line, t.column, self.filename)
            
            sizes = []
            while self._at(TokenType.LBRACKET):
                self._advance()
                sizes.append(self._expression())
                self._expect(TokenType.RBRACKET, "Expected ']' after array size")
            
            if not sizes:
                raise ParserError("Expected array dimensions (e.g. [10]) after type in 'new'", t.line, t.column, self.filename)
            
            return ast.ArrayAllocation(line=t.line, column=t.column, base_type=base, sizes=sizes)


        raise ParserError(f"Unexpected token: {t.value!r}", t.line, t.column, self.filename)

    def _parse_interpolated(self, t: Token) -> ast.InterpolatedString:
        """Split 'Hello {name}!' into parts."""
        parts = []
        raw = t.value
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                j = raw.index("}", i)
                var_name = raw[i + 1:j].strip()
                parts.append(ast.Identifier(line=t.line, column=t.column, name=var_name))
                i = j + 1
            else:
                j = raw.find("{", i)
                if j == -1:
                    j = len(raw)
                parts.append(raw[i:j])
                i = j
        return ast.InterpolatedString(line=t.line, column=t.column, parts=parts)
