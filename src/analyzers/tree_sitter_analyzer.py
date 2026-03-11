"""Tree-sitter static analysis (Python-first).

Extracts:
- imports
- top-level functions
- classes and inheritance

Computes:
- LOC (non-empty non-comment lines)
- lightweight complexity signals (keyword counts)

Design note: parser interface can be extended for SQL/YAML/JS/TS later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportRecord:
    kind: str  # "import" | "from"
    module: str
    symbol: str | None = None


@dataclass(frozen=True)
class FunctionRecord:
    name: str
    line_start: int
    line_end: int
    is_public: bool


@dataclass(frozen=True)
class ClassRecord:
    name: str
    bases: list[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0


@dataclass(frozen=True)
class PythonModuleFacts:
    imports: list[ImportRecord] = field(default_factory=list)
    functions: list[FunctionRecord] = field(default_factory=list)
    classes: list[ClassRecord] = field(default_factory=list)
    loc: int = 0
    complexity_score: float = 0.0
    parse_ok: bool = True
    error: str | None = None


def _line_of(source: bytes, byte_offset: int) -> int:
    return source[:byte_offset].count(b"\n") + 1


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def analyze_python_source(content: bytes, *, path: str = "<memory>") -> PythonModuleFacts:
    """Analyze python source bytes. Never raises on parse errors."""
    try:
        import tree_sitter
        import tree_sitter_python as tspython
    except Exception as e:
        return PythonModuleFacts(parse_ok=False, error=f"tree-sitter unavailable: {e}")

    try:
        lang = tree_sitter.Language(tspython.language())
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(content)
        root = tree.root_node
    except Exception as e:
        return PythonModuleFacts(parse_ok=False, error=str(e))

    if root.has_error:
        logger.warning("Parse errors in %s; best-effort extraction", path)

    imports: list[ImportRecord] = []
    functions: list[FunctionRecord] = []
    classes: list[ClassRecord] = []

    def walk(node):
        t = node.type
        if t == "import_statement":
            _extract_import_statement(node, content, imports)
        elif t == "import_from_statement":
            _extract_import_from_statement(node, content, imports)
        elif t == "function_definition":
            fr = _extract_function(node, content)
            if fr is not None:
                functions.append(fr)
        elif t == "class_definition":
            cr = _extract_class(node, content)
            if cr is not None:
                classes.append(cr)
        for ch in node.children:
            walk(ch)

    try:
        walk(root)
    except Exception as e:
        # very defensive: tree-sitter nodes sometimes surprise
        logger.warning("Failed walking AST for %s: %s", path, e)
        return PythonModuleFacts(parse_ok=False, error=str(e))

    loc = _compute_loc(content)
    complexity = _compute_complexity(content, len(functions), len(classes))

    return PythonModuleFacts(
        imports=imports,
        functions=functions,
        classes=classes,
        loc=loc,
        complexity_score=complexity,
        parse_ok=True,
    )


def _compute_loc(content: bytes) -> int:
    loc = 0
    for raw in content.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith(b"#"):
            continue
        loc += 1
    return loc


def _compute_complexity(content: bytes, num_functions: int, num_classes: int) -> float:
    text = content.decode("utf-8", errors="replace")
    score = 0.0
    for kw in ("if ", "elif ", "for ", "while ", "try:", "except ", "with "):
        score += text.count(kw) * 0.5
    score += num_functions * 1.0
    score += num_classes * 2.0
    return round(score, 2)


def _extract_import_statement(node, source: bytes, out: list[ImportRecord]) -> None:
    # import a, b.c
    for ch in node.children:
        if ch.type == "dotted_name":
            out.append(ImportRecord(kind="import", module=_node_text(ch, source)))


def _extract_import_from_statement(node, source: bytes, out: list[ImportRecord]) -> None:
    # from a.b import c
    module_target: str | None = None
    seen_import = False
    for ch in node.children:
        if ch.type == "import":
            seen_import = True
            continue
        if ch.type == "dotted_name":
            txt = _node_text(ch, source)
            if not seen_import:
                module_target = txt
            else:
                out.append(ImportRecord(kind="from", module=module_target or txt, symbol=txt if module_target else None))
        elif ch.type == "wildcard_import" and module_target:
            out.append(ImportRecord(kind="from", module=module_target, symbol="*"))


def _extract_function(node, source: bytes) -> FunctionRecord | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node, source)
    start = _line_of(source, node.start_byte)
    end = _line_of(source, node.end_byte)
    is_public = bool(name) and not name.startswith("_")
    return FunctionRecord(name=name, line_start=start, line_end=end, is_public=is_public)


def _extract_class(node, source: bytes) -> ClassRecord | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node, source)
    bases: list[str] = []
    supers = node.child_by_field_name("superclasses")
    if supers is not None:
        for ch in supers.children:
            if ch.type in ("(", ",", ")"):
                continue
            bases.append(_node_text(ch, source))
    start = _line_of(source, node.start_byte)
    end = _line_of(source, node.end_byte)
    return ClassRecord(name=name, bases=bases, line_start=start, line_end=end)
