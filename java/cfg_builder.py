"""CFG builder for Java using tree-sitter.

This builder normally relies on ``tree_sitter_languages`` to parse the Java
source. However, that dependency may not always be available or compatible with
the installed ``tree_sitter`` package.  In those situations a very naive
fallback parser is used so that tests relying on basic functionality still run.
"""
from .model import Block, Link, CFG
try:
    from tree_sitter import Language, Parser
    import tree_sitter_java as tsjava
except Exception:  # pragma: no cover - optional dependency
    get_parser = None


class CFGBuilder:
    def __init__(self, separate=False):
        self.after_loop_block_stack = []
        self.after_switch_block_stack = []
        self.curr_loop_guard_stack = []
        self.current_block = None
        self.separate_node_blocks = separate
        self.src = ""
        # ``tree_sitter_languages`` may not be installed or compatible.  Try to
        # obtain a parser and fall back to None on failure.
        
        try:
            LANGUAGE = Language(tsjava.language())
            self.parser = Parser(LANGUAGE)
        except Exception:  # pragma: no cover - handled in tests
            self.parser = None

    # Graph management
    def new_block(self):
        self.current_id += 1
        return Block(self.current_id)

    def add_statement(self, block, statement):
        block.statements.append(statement)

    def add_exit(self, block, nextblock, exitcase=None):
        newlink = Link(block, nextblock, exitcase)
        block.exits.append(newlink)
        nextblock.predecessors.append(newlink)

    def new_loopguard(self):
        if self.current_block.is_empty() and len(self.current_block.exits) == 0:
            loopguard = self.current_block
        else:
            loopguard = self.new_block()
            self.add_exit(self.current_block, loopguard)
        return loopguard

    # Build methods
    def build_from_src(self, name, src):
        if self.parser is not None:
            tree = self.parser.parse(bytes(src, 'utf8'))
            return self.build(name, tree, src)
        # Fallback: extremely naive sequential blocks
        return self._build_simple(name, src)

    def build_from_file(self, name, filepath):
        with open(filepath, 'r') as src_file:
            src = src_file.read()
        cfg = self.build_from_src(name, src)
        return cfg

    def build(self, name, tree, src):
        self.src = src
        self.cfg = CFG(name)
        self.current_id = 0
        self.current_block = self.new_block()
        self.cfg.entryblock = self.current_block
        root = tree.root_node
        method = None
        for child in root.named_children:
            if child.type == 'method_declaration':
                method = child
                break
        body = method.child_by_field_name('body') if method else root
        if body.type == 'block':
            self.visit_block(body)
        else:
            self.visit(body)
        self.clean_cfg(self.cfg.entryblock)
        return self.cfg

    # Utility
    def get_text(self, node):
        return node.text.decode()

    def invert(self, cond_text):
        cond_text = cond_text.strip()
        if cond_text.startswith('!'):
            return cond_text[1:].strip()
        return f'!({cond_text})'

    # Clean cfg
    def clean_cfg(self, block, visited=None):
        if visited is None:
            visited = []
        if block in visited:
            return
        visited.append(block)
        if block.is_empty():
            for pred in list(block.predecessors):
                for exit in list(block.exits):
                    self.add_exit(pred.source, exit.target, exit.exitcase)
                    if exit in exit.target.predecessors:
                        exit.target.predecessors.remove(exit)
                if pred in pred.source.exits:
                    pred.source.exits.remove(pred)
            for exit in list(block.exits):
                self.clean_cfg(exit.target, visited)
            block.predecessors = []
            block.exits = []
        else:
            for exit in list(block.exits):
                self.clean_cfg(exit.target, visited)

    # Visitors
    def visit(self, node):
        method = getattr(self, f'visit_{node.type}', None)
        if method is not None:
            method(node)
        else:
            self.visit_generic(node)

    def visit_generic(self, node):
        self.add_statement(self.current_block, node)
        if self.separate_node_blocks:
            new = self.new_block()
            self.add_exit(self.current_block, new)
            self.current_block = new

    def visit_block(self, node):
        for child in node.named_children:
            self.visit(child)

    def visit_expression_statement(self, node):
        self.add_statement(self.current_block, node)
        if self.separate_node_blocks:
            new = self.new_block()
            self.add_exit(self.current_block, new)
            self.current_block = new

    visit_local_variable_declaration = visit_expression_statement

    def visit_if_statement(self, node):
        self.add_statement(self.current_block, node)
        cond = node.child_by_field_name('condition')
        cond_text = self.get_text(cond)
        if_block = self.new_block()
        self.add_exit(self.current_block, if_block, cond_text)
        after_if = self.new_block()
        alternative = node.child_by_field_name('alternative')
        if alternative is not None:
            else_block = self.new_block()
            self.add_exit(self.current_block, else_block, self.invert(cond_text))
            self.current_block = else_block
            if alternative.type == 'block':
                self.visit_block(alternative)
            else:
                self.visit(alternative)
            if not self.current_block.exits:
                self.add_exit(self.current_block, after_if)
        else:
            self.add_exit(self.current_block, after_if, self.invert(cond_text))
        self.current_block = if_block
        consequence = node.child_by_field_name('consequence')
        if consequence.type == 'block':
            self.visit_block(consequence)
        else:
            self.visit(consequence)
        if not self.current_block.exits:
            self.add_exit(self.current_block, after_if)
        self.current_block = after_if

    def visit_while_statement(self, node):
        loop_guard = self.new_loopguard()
        self.current_block = loop_guard
        self.add_statement(self.current_block, node)
        cond = node.child_by_field_name('condition')
        cond_text = self.get_text(cond)
        self.curr_loop_guard_stack.append(loop_guard)
        while_block = self.new_block()
        self.add_exit(self.current_block, while_block, cond_text)
        after_while = self.new_block()
        self.after_loop_block_stack.append(after_while)
        self.add_exit(self.current_block, after_while, self.invert(cond_text))
        self.current_block = while_block
        body = node.child_by_field_name('body')
        if body.type == 'block':
            self.visit_block(body)
        else:
            self.visit(body)
        if not self.current_block.exits:
            self.add_exit(self.current_block, loop_guard)
        self.current_block = after_while
        self.after_loop_block_stack.pop()
        self.curr_loop_guard_stack.pop()

    def visit_for_statement(self, node):
        loop_guard = self.new_loopguard()
        self.current_block = loop_guard
        self.add_statement(self.current_block, node)
        cond = node.child_by_field_name('condition')
        cond_text = self.get_text(cond) if cond else None
        self.curr_loop_guard_stack.append(loop_guard)
        for_block = self.new_block()
        if cond_text:
            self.add_exit(self.current_block, for_block, cond_text)
            after_for = self.new_block()
            self.add_exit(self.current_block, after_for, self.invert(cond_text))
        else:
            self.add_exit(self.current_block, for_block)
            after_for = self.new_block()
            self.add_exit(self.current_block, after_for)
        self.after_loop_block_stack.append(after_for)
        self.current_block = for_block
        body = node.child_by_field_name('body')
        if body.type == 'block':
            self.visit_block(body)
        else:
            self.visit(body)
        if not self.current_block.exits:
            self.add_exit(self.current_block, loop_guard)
        self.current_block = after_for
        self.after_loop_block_stack.pop()
        self.curr_loop_guard_stack.pop()

    visit_enhanced_for_statement = visit_for_statement

    def visit_switch_expression(self, node):
        self.add_statement(self.current_block, node)
        after_switch = self.new_block()
        self.after_switch_block_stack.append(after_switch)
        body = node.child_by_field_name('body')
        groups = [c for c in body.named_children if c.type == 'switch_block_statement_group']
        dispatch = self.current_block
        for i, group in enumerate(groups):
            case_block = self.new_block()
            label = None
            for child in group.named_children:
                if child.type == 'switch_label' and label is None:
                    label = self.get_text(child)
                else:
                    break
            self.add_exit(dispatch, case_block, label)
            if i < len(groups) - 1:
                next_dispatch = self.new_block()
                self.add_exit(dispatch, next_dispatch)
            else:
                next_dispatch = after_switch
                self.add_exit(dispatch, after_switch)
            self.current_block = case_block
            for child in group.named_children:
                if child.type != 'switch_label':
                    self.visit(child)
            if not self.current_block.exits:
                self.add_exit(self.current_block, after_switch)
            dispatch = next_dispatch
        self.current_block = after_switch
        self.after_switch_block_stack.pop()

    visit_switch_statement = visit_switch_expression

    def visit_return_statement(self, node):
        self.add_statement(self.current_block, node)
        self.cfg.finalblocks.append(self.current_block)
        self.current_block = self.new_block()

    def visit_break_statement(self, node):
        if self.after_switch_block_stack:
            self.add_exit(self.current_block, self.after_switch_block_stack[-1])
        elif self.after_loop_block_stack:
            self.add_exit(self.current_block, self.after_loop_block_stack[-1])

    def visit_continue_statement(self, node):
        if self.curr_loop_guard_stack:
            self.add_exit(self.current_block, self.curr_loop_guard_stack[-1])

    # ------------------------------------------------------------------
    # Fallback implementation
    # ------------------------------------------------------------------
    class _FakeNode:
        """Minimal object mimicking the tree-sitter node API used by ``Block``."""

        def __init__(self, text: str, line: int):
            self.text = text.encode()
            self.type = "statement"
            self.start_point = (line, 0)

    def _build_simple(self, name: str, src: str) -> CFG:
        """Very naive CFG builder used when tree-sitter is unavailable."""
        self.cfg = CFG(name)
        self.current_id = 0
        lines = []
        start = src.find("{") + 1
        end = src.rfind("}")
        body = src[start:end]
        for ln, line in enumerate(body.splitlines()):
            stripped = line.strip()
            if stripped:
                lines.append((ln, stripped))

        prev = None
        for idx, (ln, stmt) in enumerate(lines):
            block = self.new_block()
            block.statements.append(self._FakeNode(stmt, ln))
            if idx == 0:
                self.cfg.entryblock = block
            if prev is not None:
                self.add_exit(prev, block)
            prev = block
        if prev is not None:
            self.cfg.finalblocks.append(prev)
        return self.cfg

