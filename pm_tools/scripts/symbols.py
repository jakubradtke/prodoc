"""
Symbols, conditional text and document variants for the prodoc preprocessor.

Symbols are name -> value pairs available in two ways:

  * ``{{NAME}}`` in the text is replaced by the value (only defined names are replaced;
    ``\\{{NAME}}`` keeps the literal ``{{NAME}}``),
  * ``<!--if:EXPR-->`` ... ``<!--elif:EXPR-->`` ... ``<!--else-->`` ... ``<!--endif-->``
    keep or drop a block of text depending on a Python expression over the symbols.

Sources of symbols, highest priority first:

  1. command line: ``--define NAME=VALUE`` and ``--variant NAME``,
  2. ``build.cfg`` found upwards from the document folder: ``symbols``, ``variants``, ``releases``,
  3. include parameters ``[_file.md||NAME:"value"]`` (scope: the included file),
  4. ``symbols:`` in the YAML header of the file (adds only missing names).

``RELEASE`` is special: when ``build.cfg`` lists ``releases`` in order, the value becomes a
``Release`` object, so ``RELEASE >= "26.H1"`` compares positions in that list.

All processing happens on the raw text, before tokenization, so plugins inside a dropped
block never run. Python 2.
"""

import os
import re

import yaml

import util

__all__ = ["SymbolError", "Release", "load_build_config", "make_symbols", "read_header",
           "header_variants", "apply_header", "substitute", "filter_blocks",
           "parse_include_params", "preprocess_text", "to_str"]


class SymbolError(Exception):
    pass


def to_str(value):
    """Byte string (UTF-8) of a symbol value, for insertion into the document text."""
    if isinstance(value, unicode):
        return value.encode("utf-8")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class Release(object):
    """A release name with an order defined by the ``releases`` list of build.cfg.
    Compares with other Release objects and with strings naming a listed release."""

    def __init__(self, name, releases):
        self.name = to_str(name)
        self.releases = [to_str(r) for r in releases]
        if self.name not in self.releases:
            raise SymbolError("Unknown release '%s'. Releases defined in build.cfg: %s"
                              % (self.name, ", ".join(self.releases) or "(none)"))
        self.index = self.releases.index(self.name)

    def _index(self, other):
        if isinstance(other, Release):
            return other.index
        other = to_str(other)
        if other not in self.releases:
            raise SymbolError("Unknown release '%s' in comparison. Releases defined in build.cfg: %s"
                              % (other, ", ".join(self.releases)))
        return self.releases.index(other)

    def __eq__(self, other):
        try:
            return self.index == self._index(other)
        except SymbolError:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        return self.index < self._index(other)

    def __le__(self, other):
        return self.index <= self._index(other)

    def __gt__(self, other):
        return self.index > self._index(other)

    def __ge__(self, other):
        return self.index >= self._index(other)

    def __hash__(self):
        return hash(self.name)

    def __str__(self):
        return self.name

    def __repr__(self):
        return "Release(%r)" % self.name


# ---------------------------------------------------------------------------- build.cfg

_config_cache = {}


def load_build_config(dirname):
    """``symbols``, ``variants`` and ``releases`` from the nearest build.cfg above dirname.
    Returns a dict with those three keys (empty when there is no build.cfg)."""
    dirname = os.path.normcase(os.path.abspath(dirname))
    if dirname in _config_cache:
        return _config_cache[dirname]
    cfg = util.get_config(dirname, skip_hooks=True) or {}
    out = {
        "root": cfg.get("root"),
        "symbols": dict(cfg.get("symbols") or {}),
        "variants": dict(cfg.get("variants") or {}),
        "releases": list(cfg.get("releases") or []),
    }
    if not isinstance(cfg.get("symbols", {}), dict):
        raise SymbolError("build.cfg: 'symbols' must be a dict")
    if not isinstance(cfg.get("variants", {}), dict):
        raise SymbolError("build.cfg: 'variants' must be a dict of variant name -> dict of symbols")
    for name, syms in out["variants"].items():
        if not isinstance(syms, dict):
            raise SymbolError("build.cfg: variant '%s' must map to a dict of symbols" % name)
    _config_cache[dirname] = out
    return out


def _resolve_release(symbols, releases):
    """Turn a string RELEASE into a Release object when releases are defined."""
    value = symbols.get("RELEASE")
    if value is None or isinstance(value, Release) or not releases:
        return
    symbols["RELEASE"] = Release(value, releases)


def make_symbols(cfg, variant=None, defines=None, fmt="html"):
    """Symbols for one build: build.cfg symbols, then the variant, then --define values,
    plus the built-in VARIANT and FMT."""
    symbols = dict(cfg["symbols"])
    if variant:
        if variant in cfg["variants"]:
            symbols.update(cfg["variants"][variant])
        elif cfg["variants"]:
            raise SymbolError("Unknown variant '%s'. Variants defined in build.cfg: %s"
                              % (variant, ", ".join(sorted(cfg["variants"]))))
    for item in defines or []:
        if "=" not in item:
            raise SymbolError("--define expects NAME=VALUE, got '%s'" % item)
        name, value = item.split("=", 1)
        name = name.strip()
        if not re.match(r"^[A-Za-z_]\w*$", name):
            raise SymbolError("--define: invalid symbol name '%s'" % name)
        symbols[name] = value
    symbols["VARIANT"] = variant or ""
    symbols["FMT"] = fmt
    _resolve_release(symbols, cfg["releases"])
    return symbols


# ---------------------------------------------------------------------------- YAML header

HEADER_RE = re.compile(r"\A\s*---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S)


def read_header(text):
    """Dict from the YAML front matter of text, or {} (also when the YAML is invalid:
    pandoc reports that later, after symbol substitution)."""
    m = HEADER_RE.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def header_variants(header):
    """List of variant names from ``variants:`` of a YAML header (strings, in order)."""
    variants = header.get("variants")
    if variants is None:
        return []
    if isinstance(variants, basestring):
        variants = [v.strip() for v in variants.split(",") if v.strip()]
    if not isinstance(variants, (list, tuple)):
        raise SymbolError("YAML 'variants' must be a list of variant names")
    return [to_str(v) for v in variants]


def apply_header(symbols, header, releases):
    """Add ``symbols:`` of a YAML header to symbols without overriding existing names."""
    extra = header.get("symbols") or {}
    if not isinstance(extra, dict):
        raise SymbolError("YAML 'symbols' must be a mapping of name: value")
    for name, value in extra.items():
        name = to_str(name)
        if name not in symbols:
            symbols[name] = value
    _resolve_release(symbols, releases)
    return symbols


# ---------------------------------------------------------------------------- substitution

SUBST_RE = re.compile(r"(\\?)\{\{([A-Za-z_]\w*)\}\}")


def substitute(text, symbols):
    """Replace ``{{NAME}}`` of defined symbols. ``\\{{NAME}}`` -> literal ``{{NAME}}``.
    Unknown names stay untouched (backslash included)."""
    if not symbols:
        return text

    def repl(m):
        escaped, name = m.group(1), m.group(2)
        if name not in symbols:
            return m.group(0)
        if escaped:
            return "{{%s}}" % name
        return to_str(symbols[name])

    return SUBST_RE.sub(repl, text)


# ---------------------------------------------------------------------------- conditionals

MARK_RE = re.compile(r"<!--\s*(if|elif|else|endif)\b\s*(?::\s*(.*?))?\s*-->", re.S)

_SAFE_BUILTINS = {"len": len, "str": str, "int": int, "float": float,
                  "True": True, "False": False, "None": None}


def safe_eval(expr, symbols, where, verbose=False):
    """Evaluate a condition over the symbols. An undefined name gives False (idiom for
    "is the symbol defined"); a syntax or type error stops the build."""
    env = dict(symbols)
    env["__builtins__"] = dict(_SAFE_BUILTINS, defined=lambda name: name in symbols)
    try:
        return bool(eval(expr, env))
    except NameError as e:
        if verbose:
            print "%s: condition '%s' is false: %s" % (where, expr, e)
        return False
    except SymbolError as e:
        raise SymbolError("%s: in condition '%s': %s" % (where, expr, e))
    except Exception as e:
        raise SymbolError("%s: cannot evaluate condition '%s': %s: %s"
                          % (where, expr, e.__class__.__name__, e))


FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
WORD_RE = re.compile(r"[A-Za-z_][\w\-]*")


def code_ranges(text, plugin_tokens=()):
    """(start, end) offsets of code in text: fenced code blocks (except plugin blocks such as
    ```plantuml(...), where conditions stay active) and inline code spans. Markers inside
    code are documentation, for example `<!--if:X-->` in a user guide."""
    ranges = []
    pos = 0
    fence = None  # (char, length, start offset, protected)
    for line in text.splitlines(True):
        m = FENCE_RE.match(line.rstrip("\r\n"))
        if fence is None:
            if m:
                word = WORD_RE.search(m.group(2))
                is_plugin = bool(word) and word.group(0).lower() in plugin_tokens
                fence = (m.group(1)[0], len(m.group(1)), pos, not is_plugin)
            else:
                for c in CODE_SPAN_RE.finditer(line):
                    ranges.append((pos + c.start(), pos + c.end()))
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and not m.group(2).strip():
            if fence[3]:
                ranges.append((fence[2], pos + len(line)))
            fence = None
        pos += len(line)
    if fence is not None and fence[3]:
        ranges.append((fence[2], len(text)))
    return ranges


def filter_blocks(text, symbols, fname="<text>", verbose=False, plugin_tokens=()):
    """Apply ``<!--if:-->`` / ``<!--elif:-->`` / ``<!--else-->`` / ``<!--endif-->`` blocks.
    Blocks nest. The markers are removed from the output; the text of inactive blocks too.
    Markers inside inline code and fenced code blocks are left as text (see code_ranges)."""
    out = []
    stack = []  # frames: [parent_active, taken, active, had_else, line]
    pos = 0
    active = True
    protected = code_ranges(text, plugin_tokens) if "<!--" in text else []

    def line_of(offset):
        return text.count("\n", 0, offset) + 1

    def in_code(offset):
        return any(a <= offset < b for a, b in protected)

    search_from = 0
    while True:
        m = MARK_RE.search(text, search_from)
        if not m:
            break
        if in_code(m.start()):
            search_from = m.start() + 1
            continue
        search_from = m.end()
        kind, expr = m.group(1), (m.group(2) or "").strip()
        where = "%s:%d" % (fname, line_of(m.start()))
        if active:
            out.append(text[pos:m.start()])
        pos = m.end()
        if kind == "if":
            if not expr:
                raise SymbolError("%s: <!--if--> without a condition" % where)
            cond = active and safe_eval(expr, symbols, where, verbose)
            stack.append([active, cond, cond, False, where])
            active = cond
        elif kind == "elif":
            if not stack:
                raise SymbolError("%s: <!--elif--> without <!--if-->" % where)
            if not expr:
                raise SymbolError("%s: <!--elif--> without a condition" % where)
            frame = stack[-1]
            if frame[3]:
                raise SymbolError("%s: <!--elif--> after <!--else-->" % where)
            cond = frame[0] and not frame[1] and safe_eval(expr, symbols, where, verbose)
            frame[1] = frame[1] or cond
            frame[2] = active = cond
        elif kind == "else":
            if not stack:
                raise SymbolError("%s: <!--else--> without <!--if-->" % where)
            if expr:
                raise SymbolError("%s: <!--else--> must not have a condition" % where)
            frame = stack[-1]
            if frame[3]:
                raise SymbolError("%s: second <!--else--> in one block" % where)
            frame[3] = True
            frame[2] = active = frame[0] and not frame[1]
            frame[1] = True
        else:  # endif
            if not stack:
                raise SymbolError("%s: <!--endif--> without <!--if-->" % where)
            if expr:
                raise SymbolError("%s: <!--endif--> must not have a condition" % where)
            frame = stack.pop()
            active = frame[0]
    if stack:
        raise SymbolError("%s: <!--if--> block opened at %s is not closed (missing <!--endif-->)"
                          % (fname, stack[-1][4]))
    if active:
        out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------- includes

PARAM_RE = re.compile(r"""\s*([A-Za-z_]\w*)\s*:\s*(?:"([^"]*)"|'([^']*)'|([^,]*))\s*(?:,|$)""")


def parse_include_params(param_str):
    """'RELEASE:"26.H2",OS:Linux' -> {'RELEASE': '26.H2', 'OS': 'Linux'} (all values strings)."""
    out = {}
    pos = 0
    param_str = param_str.strip()
    while pos < len(param_str):
        m = PARAM_RE.match(param_str, pos)
        if not m or m.end() == pos:
            raise SymbolError("Invalid include parameters: '%s' (expected NAME:\"value\",NAME2:value)"
                              % param_str)
        name, dq, sq, bare = m.groups()
        value = dq if dq is not None else (sq if sq is not None else (bare or "").strip())
        out[name] = value
        pos = m.end()
    return out


# ---------------------------------------------------------------------------- pipeline

def preprocess_text(text, symbols, releases, fname, verbose=False, plugin_tokens=()):
    """YAML ``symbols:`` -> ``{{NAME}}`` substitution -> conditional blocks.
    Modifies ``symbols`` in place (adds the header symbols). Returns the new text."""
    header = read_header(text)
    apply_header(symbols, header, releases)
    text = substitute(text, symbols)
    text = filter_blocks(text, symbols, fname, verbose, plugin_tokens)
    return text
