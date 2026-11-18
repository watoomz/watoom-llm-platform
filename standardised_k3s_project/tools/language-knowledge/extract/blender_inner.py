"""Dump live RNA metadata. Execute with Blender, never with project files loaded."""

import json
import os
import sys
from pathlib import Path

import bpy


def property_definition(prop):
    """Keep RNA declaration order and distinguish absent defaults from null."""
    result = {
        "name": prop.identifier,
        "type": prop.type,
        "subtype": getattr(prop, "subtype", "NONE"),
        "description": prop.description,
        "is_readonly": prop.is_readonly,
        "is_required": prop.is_required,
        "is_output": prop.is_output,
        "is_enum_flag": getattr(prop, "is_enum_flag", False),
        "array_length": getattr(prop, "array_length", 0),
        "is_array": getattr(prop, "is_array", False),
        "array_dimensions": list(getattr(prop, "array_dimensions", ())),
    }
    fixed_type = getattr(prop, "fixed_type", None)
    if fixed_type is not None:
        result["fixed_type"] = fixed_type.identifier
    if result["is_enum_flag"]:
        result["default"] = sorted(prop.default_flag)
    elif prop.type == "POINTER":
        # RNA pointers have no stored default; Blender's _rna_info likewise
        # represents their default as None.
        result["default"] = None
    elif result["is_array"]:
        result["default"] = list(prop.default_array)
    else:
        absent = object()
        value = getattr(prop, "default", absent)
        if value is not absent:
            result["default"] = sorted(value) if isinstance(value, set) else value
    if prop.type == "ENUM":
        # Consume the live iterator directly: dynamic item memory is owned by
        # that iterator. Fall back to static items for context-dependent enums.
        items = prop.enum_items
        if not items:
            items = prop.enum_items_static
        result["enum_items"] = [
            {"identifier": item.identifier, "name": item.name,
             "description": item.description, "value": item.value}
            for item in items
        ]
    return result


def members(collection):
    # Iteration includes inherited definitions shadowed by a derived member.
    # Name lookup resolves the member that Python actually exposes on this type.
    return [collection[name] for name in dict.fromkeys(
        item.identifier for item in collection)]


def properties(collection):
    return [property_definition(prop) for prop in members(collection)
            if prop.identifier != "rna_type"]


def dump():
    operators = []
    for module in sorted(dir(bpy.ops)):
        namespace = getattr(bpy.ops, module)
        for name in sorted(dir(namespace)):
            operator = getattr(namespace, name)
            rna = operator.get_rna_type()
            operators.append({
                "module": module, "name": name, "bl_label": rna.name,
                "description": rna.description,
                "rna_signature": operator.__doc__.splitlines()[0],
                "properties": properties(rna.properties),
            })
    structs = []
    for name in sorted(dir(bpy.types)):
        cls = getattr(bpy.types, name)
        rna = getattr(cls, "bl_rna", None)
        if rna is None:
            continue
        structs.append({
            "name": name, "description": rna.description,
            "properties": properties(rna.properties),
            "functions": [
                {"name": fn.identifier, "description": fn.description,
                 "use_self": fn.use_self, "use_self_type": fn.use_self_type,
                 "parameters": properties(fn.parameters)}
                for fn in members(rna.functions)
            ],
        })
    return {"version": ".".join(map(str, bpy.app.version)),
            "operators": operators, "structs": structs}


if __name__ == "__main__":
    output = Path(sys.argv[sys.argv.index("--") + 1])
    output.write_text(json.dumps(dump(), sort_keys=True, ensure_ascii=True,
                                 allow_nan=False, separators=(",", ":")) + "\n",
                      encoding="utf-8")
    # Blender 5.2.3 can hang in audio teardown even with -noaudio in a sandbox.
    # This dedicated factory-startup process has no work to save. write_text has
    # closed the complete dump; bypass only teardown, never extraction failures.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
