"""Minimal dependency-free BibTeX parser (handles nested braces and quoted values)."""
import re


def _read_value(s, i):
    """Read a field value starting at s[i]; return (value, new_index)."""
    while s[i].isspace():
        i += 1
    if s[i] == "{":
        depth, j = 0, i
        while True:
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1 : j], j + 1
            j += 1
    if s[i] == '"':
        j = i + 1
        depth = 0
        while not (s[j] == '"' and depth == 0):
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            j += 1
        return s[i + 1 : j], j + 1
    m = re.match(r"[^,}\s]+", s[i:])
    return m.group(0), i + m.end()


def parse_bib(text):
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        etype = m.group(1).lower()
        if etype in ("comment", "string", "preamble"):
            continue
        entry = {"ENTRYTYPE": etype, "ID": m.group(2)}
        i = m.end()
        while True:
            while i < len(text) and text[i] in " \t\r\n,":
                i += 1
            if i >= len(text) or text[i] == "}":
                break
            fm = re.match(r"([A-Za-z_\-]+)\s*=", text[i:])
            if not fm:
                break
            name = fm.group(1).lower()
            val, i = _read_value(text, i + fm.end())
            entry[name] = re.sub(r"\s+", " ", val).strip()
        while i < len(text) and text[i] != "}":
            i += 1
        entry["_raw"] = text[m.start() : i + 1]
        entries.append(entry)
    return entries


TEX_SYMBOLS = {
    "tau": "τ", "nu": "ν", "mu": "μ", "pi": "π", "sigma": "σ", "gamma": "γ", "ell": "ℓ",
    "rho": "ρ", "pm": "±", "to": "→", "rightarrow": "→", "textrightarrow": "→",
    "textendash": "–", "varnothing": "∅", "cdot": "·", "times": "×",
}
SUPERSCRIPTS = str.maketrans("+-−±*0123456789", "⁺⁻⁻±*⁰¹²³⁴⁵⁶⁷⁸⁹")


def clean(s):
    """Render a BibTeX string as readable Unicode text for display."""
    s = re.sub(r"\\(ensuremath|text|rm|small|mathrm)\b\s*", "", s)
    s = re.sub(r"\\sqrt\s*\{?\s*s\s*\}?", "√s", s)
    s = re.sub(r"\\bar\s*\{?\s*(\w)\s*\}?", "\\1\u0304", s)
    s = re.sub(r"\\([a-zA-Z]+)\s*", lambda m: TEX_SYMBOLS.get(m.group(1), "") , s)
    s = re.sub(r"\^\{?([+\-*0-9]+)\}?", lambda m: m.group(1).translate(SUPERSCRIPTS), s)
    s = re.sub(r"_\{?([^{}\s$]+)\}?", r"\1", s)
    s = s.replace("{", "").replace("}", "").replace("$", "").replace("^", "")
    s = s.replace("\\&", "&").replace("&", "&").replace("~", " ").replace("--", "–").replace("\\", "")
    return re.sub(r"\s+", " ", s).strip()
