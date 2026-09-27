"""LZString compressToEncodedURIComponent / decompressFromEncodedURIComponent (pieroxy/lz-string 포팅).

네이버페이 부동산 지도 URL의 layer 파라미터가 이 형식이다.
"""
from __future__ import annotations

_KEY = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-$"


def compress_uri(text: str) -> str:
    if not text:
        return ""
    bits_per_char = 6
    ctx_dict: dict[str, int] = {}
    ctx_to_create: set[str] = set()
    ctx_w = ""
    enlarge_in, dict_size, num_bits = 2, 3, 2
    out: list[str] = []
    val, pos = 0, 0

    def write_bits(value: int, n: int) -> None:
        nonlocal val, pos
        for _ in range(n):
            val = (val << 1) | (value & 1)
            if pos == bits_per_char - 1:
                pos = 0
                out.append(_KEY[val])
                val = 0
            else:
                pos += 1
            value >>= 1

    def emit_w() -> None:
        nonlocal enlarge_in, num_bits
        if ctx_w in ctx_to_create:
            code = ord(ctx_w[0])
            if code < 256:
                write_bits(0, num_bits)
                write_bits(code, 8)
            else:
                write_bits(1, num_bits)
                write_bits(code, 16)
            enlarge_in -= 1
            if enlarge_in == 0:
                enlarge_in = 2 ** num_bits
                num_bits += 1
            ctx_to_create.discard(ctx_w)
        else:
            write_bits(ctx_dict[ctx_w], num_bits)
        enlarge_in -= 1
        if enlarge_in == 0:
            enlarge_in = 2 ** num_bits
            num_bits += 1

    for c in text:
        if c not in ctx_dict:
            ctx_dict[c] = dict_size
            dict_size += 1
            ctx_to_create.add(c)
        wc = ctx_w + c
        if wc in ctx_dict:
            ctx_w = wc
        else:
            emit_w()
            ctx_dict[wc] = dict_size
            dict_size += 1
            ctx_w = c
    if ctx_w:
        emit_w()
    write_bits(2, num_bits)
    while True:
        val <<= 1
        if pos == bits_per_char - 1:
            out.append(_KEY[val])
            break
        pos += 1
    return "".join(out)


def decompress_uri(inp: str) -> str | None:
    if not inp:
        return ""
    inp = inp.replace(" ", "+")
    length, reset = len(inp), 32
    dictionary: dict[int, str] = {}
    enlarge_in, dict_size, num_bits = 4, 4, 3
    data_val, data_pos, data_idx = _KEY.index(inp[0]), reset, 1

    def bits(n: int) -> int:
        nonlocal data_val, data_pos, data_idx
        res, p = 0, 1
        for _ in range(n):
            resb = data_val & data_pos
            data_pos >>= 1
            if data_pos == 0:
                data_pos = reset
                data_val = _KEY.index(inp[data_idx]) if data_idx < length else 0
                data_idx += 1
            res |= (1 if resb else 0) * p
            p <<= 1
        return res

    nxt = bits(2)
    if nxt == 2:
        return ""
    w = chr(bits(8 if nxt == 0 else 16))
    dictionary[3] = w
    result = [w]
    while True:
        if data_idx > length:
            return "".join(result)
        cc = bits(num_bits)
        if cc in (0, 1):
            dictionary[dict_size] = chr(bits(8 if cc == 0 else 16))
            dict_size += 1
            cc = dict_size - 1
            enlarge_in -= 1
        elif cc == 2:
            return "".join(result)
        if enlarge_in == 0:
            enlarge_in = 2 ** num_bits
            num_bits += 1
        if cc in dictionary:
            entry = dictionary[cc]
        elif cc == dict_size:
            entry = w + w[0]
        else:
            return None
        result.append(entry)
        dictionary[dict_size] = w + entry[0]
        dict_size += 1
        enlarge_in -= 1
        w = entry
        if enlarge_in == 0:
            enlarge_in = 2 ** num_bits
            num_bits += 1
