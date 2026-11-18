"""Tiny schema checker for profiles and presets (stdlib). A schema node is one of:
  {"t": "int|float|bool|str|rgb|hex|list|obj|any", "min":, "max":, "enum": [...], "n": len, "items": node, "fields": {name: node},
   "opt": True, "nullable": True, "pattern": regex}
check(value, node, path) -> list of error strings naming the field, the value and the allowed range. Unknown object keys are errors."""
import re


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check(v, node, path="$"):
    errs = []
    t = node.get("t", "any")
    if v is None:
        return [] if node.get("nullable") else ["%s: null not allowed" % path]
    if t == "int" and not (isinstance(v, int) and not isinstance(v, bool)):
        return ["%s: expected int, got %r" % (path, v)]
    if t == "float" and not _num(v):
        return ["%s: expected number, got %r" % (path, v)]
    if t == "bool" and not isinstance(v, bool):
        return ["%s: expected true/false, got %r" % (path, v)]
    if t == "str" and not isinstance(v, str):
        return ["%s: expected string, got %r" % (path, v)]
    if t in ("int", "float"):
        if "min" in node and v < node["min"] or "max" in node and v > node["max"]:
            errs.append("%s: %r out of range [%s, %s]" % (path, v, node.get("min"), node.get("max")))
    if t == "rgb":
        if not (isinstance(v, list) and len(v) == 3 and all(_num(x) and 0 <= x <= 1 for x in v)):
            errs.append("%s: expected [r, g, b] each 0..1, got %r" % (path, v))
    if t == "hex" and not (isinstance(v, str) and re.fullmatch(r"[0-9a-fA-F]{6}", v)):
        errs.append("%s: expected 6 hex digits, got %r" % (path, v))
    if "enum" in node and v not in node["enum"]:
        errs.append("%s: %r not one of %s" % (path, v, node["enum"]))
    if "pattern" in node and not (isinstance(v, str) and re.fullmatch(node["pattern"], v)):
        errs.append("%s: %r does not match %s" % (path, v, node["pattern"]))
    if t == "list":
        if not isinstance(v, list):
            return ["%s: expected list, got %r" % (path, v)]
        if "n" in node and len(v) != node["n"]:
            errs.append("%s: expected %d items, got %d" % (path, node["n"], len(v)))
        if "min_len" in node and len(v) < node["min_len"]:
            errs.append("%s: needs at least %d items, got %d" % (path, node["min_len"], len(v)))
        for i, x in enumerate(v):
            errs += check(x, node.get("items", {"t": "any"}), "%s[%d]" % (path, i))
    if t == "obj":
        if not isinstance(v, dict):
            return ["%s: expected object, got %r" % (path, v)]
        fields = node.get("fields", {})
        for k in v:
            if k not in fields and not k.startswith("_") and not node.get("open"):
                errs.append("%s: unknown key '%s' (allowed: %s)" % (path, k, ", ".join(sorted(fields))))
        for k, sub in fields.items():
            if k in v:
                errs += check(v[k], sub, "%s.%s" % (path, k))
            elif not sub.get("opt"):
                errs.append("%s: missing required '%s'" % (path, k))
    return errs


def merge(base, over, path="$"):
    """Deep-merge over into a copy of base. Unknown keys (not in base) raise KeyError naming the path."""
    if not isinstance(base, dict) or not isinstance(over, dict):
        return over
    out = dict(base)
    for k, v in over.items():
        if k not in base:
            raise KeyError("%s.%s: unknown override key (allowed: %s)" % (path, k, ", ".join(sorted(base))))
        out[k] = merge(base[k], v, "%s.%s" % (path, k))
    return out
