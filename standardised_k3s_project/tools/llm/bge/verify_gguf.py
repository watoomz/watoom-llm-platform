#!/usr/bin/env python3
"""Prove a third-party BGE GGUF is a faithful conversion of the official weights.

Every GGUF tensor must equal exactly one official safetensors tensor (bitwise, after
the same float16 cast for F16 tensors), every official weight must be used, the
tokenizer vocabulary must equal vocab.txt, and pooling must be CLS (BGE's pooling).
Pure Python + numpy: no converter or third-party model code is executed.
"""

import argparse, json, pathlib, struct, sys
import numpy as np

GGML = {0: np.float32, 1: np.float16}
SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
POOLING_CLS = 2


def read_gguf(path):
    data = path.read_bytes()
    pos = 0

    def take(fmt):
        nonlocal pos
        value = struct.unpack_from(fmt, data, pos)
        pos += struct.calcsize(fmt)
        return value[0]

    def string():
        nonlocal pos
        n = take("<Q")
        s = data[pos : pos + n].decode()
        pos += n
        return s

    def value(kind):
        if kind == 8:
            return string()
        if kind == 9:
            inner, n = take("<I"), take("<Q")
            return [value(inner) for _ in range(n)]
        return take(SCALAR[kind])

    if data[:4] != b"GGUF":
        raise ValueError("not a GGUF file")
    pos = 4
    version = take("<I")
    n_tensors = take("<Q")
    n_kv = take("<Q")
    meta = {}
    for _ in range(n_kv):
        key = string()
        meta[key] = value(take("<I"))
    infos = []
    for _ in range(n_tensors):
        name = string()
        dims = [take("<Q") for _ in range(take("<I"))]
        infos.append((name, dims, take("<I"), take("<Q")))
    align = meta.get("general.alignment", 32)
    start = (pos + align - 1) // align * align
    tensors = {}
    for name, dims, kind, offset in infos:
        if kind not in GGML:
            raise ValueError(f"{name}: unsupported tensor type {kind}")
        shape = tuple(reversed(dims))
        count = int(np.prod(shape))
        tensors[name] = np.frombuffer(data, GGML[kind], count, start + offset).reshape(shape)
    return version, meta, tensors


def read_safetensors(path):
    data = path.read_bytes()
    n = struct.unpack_from("<Q", data)[0]
    header = json.loads(data[8 : 8 + n])
    base = 8 + n
    out = {}
    for name, info in header.items():
        if name == "__metadata__" or name.endswith("position_ids"):
            continue  # index buffer, not a weight
        if info["dtype"] != "F32":
            raise ValueError(f"{name}: expected F32, got {info['dtype']}")
        a, b = info["data_offsets"]
        out[name] = np.frombuffer(data, np.float32, (b - a) // 4, base + a).reshape(info["shape"])
    return out


def verify(gguf_path, hf_dir):
    version, meta, gguf = read_gguf(gguf_path)
    official = read_safetensors(hf_dir / "model.safetensors")
    unused = {k for k in official if not k.endswith("position_ids") and not k.startswith("pooler.")}
    matches, failures = {}, []
    for name, tensor in gguf.items():
        found = [
            k
            for k in unused
            if official[k].shape == tensor.shape
            and np.array_equal(
                official[k].astype(tensor.dtype).view(np.uint8), np.ascontiguousarray(tensor).view(np.uint8)
            )
        ]
        if len(found) != 1:
            failures.append(f"{name}: {len(found)} exact official matches")
            continue
        matches[name] = found[0]
        unused.discard(found[0])
    if unused:
        failures.append(f"official tensors not present in GGUF: {sorted(unused)}")
    vocab = (hf_dir / "vocab.txt").read_text(encoding="utf-8").split("\n")
    vocab = vocab[:-1] if vocab and vocab[-1] == "" else vocab
    # llama.cpp stores WordPiece as phantom-space tokens: "##x" -> "x", word starts "x" -> "\u2581x".
    wpm = lambda t: t[2:] if t.startswith("##") else "\u2581" + t
    tokens = meta.get("tokenizer.ggml.tokens") or []
    if len(tokens) != len(vocab) or any(g != h and g != wpm(h) for g, h in zip(tokens, vocab)):
        failures.append("tokenizer vocabulary differs from vocab.txt")
    arch = meta.get("general.architecture")
    if arch != "bert":
        failures.append(f"architecture {arch!r}, expected 'bert'")
    if meta.get(f"{arch}.pooling_type") != POOLING_CLS:
        failures.append(f"pooling_type {meta.get(f'{arch}.pooling_type')!r}, expected CLS ({POOLING_CLS})")
    config = json.loads((hf_dir / "config.json").read_text())
    expect = {
        f"{arch}.embedding_length": config["hidden_size"],
        f"{arch}.block_count": config["num_hidden_layers"],
        f"{arch}.context_length": config["max_position_embeddings"],
        f"{arch}.attention.head_count": config["num_attention_heads"],
    }
    for key, want in expect.items():
        if meta.get(key) != want:
            failures.append(f"{key}={meta.get(key)!r}, expected {want}")
    dtypes = sorted({str(t.dtype) for t in gguf.values()})
    return {
        "gguf_version": version,
        "tensors": len(gguf),
        "matched": len(matches),
        "dtypes": dtypes,
        "embedding_length": meta.get(f"{arch}.embedding_length"),
        "context_length": meta.get(f"{arch}.context_length"),
        "pooling": "CLS" if meta.get(f"{arch}.pooling_type") == POOLING_CLS else meta.get(f"{arch}.pooling_type"),
        "vocab": len(vocab),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("gguf", type=pathlib.Path)
    p.add_argument("hf_dir", type=pathlib.Path)
    a = p.parse_args()
    result = verify(a.gguf, a.hf_dir)
    print(json.dumps(result, indent=2))
    sys.exit(result["status"] != "PASS")


if __name__ == "__main__":
    main()
