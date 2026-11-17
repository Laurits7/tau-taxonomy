#!/usr/bin/env python3
"""Build a self-contained HTML taxonomy browser from a .bib file + hand classification.

Usage:  python3 build.py [bibfile] [classification] [-o out.html] [--zotero-bib out.bib]

Normally run via ./tau_taxonomy, which serves the page so read marks / bins can be saved.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from bibparse import clean, parse_bib

HERE = Path(__file__).parent

# code -> (label, facility)
EXPERIMENTS = {
    "ATLAS": ("ATLAS", "LHC"),
    "CMS": ("CMS", "LHC"),
    "LHCb": ("LHCb", "LHC"),
    "CDF": ("CDF", "Tevatron"),
    "D0": ("DØ", "Tevatron"),
    "UA1": ("UA1", "SppS"),
    "UA2": ("UA2", "SppS"),
    "ALEPH": ("ALEPH", "LEP / SLC"),
    "DELPHI": ("DELPHI", "LEP / SLC"),
    "L3": ("L3", "LEP / SLC"),
    "OPAL": ("OPAL", "LEP / SLC"),
    "SLD": ("SLD", "LEP / SLC"),
    "LEP": ("LEP (generic / combined)", "LEP / SLC"),
    "MarkI": ("Mark I (SPEAR)", "Early e⁺e⁻ (SPEAR / PEP)"),
    "MarkII": ("Mark II (PEP)", "Early e⁺e⁻ (SPEAR / PEP)"),
    "CLEO": ("CLEO", "B factories / τ-charm"),
    "ARGUS": ("ARGUS", "B factories / τ-charm"),
    "BaBar": ("BaBar", "B factories / τ-charm"),
    "Belle": ("Belle", "B factories / τ-charm"),
    "BelleII": ("Belle II", "B factories / τ-charm"),
    "STCF": ("STCF", "B factories / τ-charm"),
    "TauFactory": ("τ factory (generic)", "B factories / τ-charm"),
    "H1": ("H1", "HERA"),
    "ZEUS": ("ZEUS", "HERA"),
    "ILD": ("ILD / ILC", "Future colliders"),
    "CLIC": ("CLIC", "Future colliders"),
    "FCCee": ("FCC-ee", "Future colliders"),
    "FutureEE": ("Future e⁺e⁻ (generic)", "Future colliders"),
    "MuonCollider": ("Muon collider", "Future colliders"),
    "DONUT": ("DONUT", "Neutrino experiments"),
    "OPERA": ("OPERA", "Neutrino experiments"),
    "IceCube": ("IceCube", "Neutrino experiments"),
    "General": ("General (experiment-agnostic)", "General"),
}
FACILITY_ORDER = ["LHC", "Tevatron", "SppS", "LEP / SLC", "Early e⁺e⁻ (SPEAR / PEP)",
                  "B factories / τ-charm", "HERA", "Future colliders",
                  "Neutrino experiments", "General"]

COLLISIONS = {
    "ee": "e⁺e⁻",
    "had": "Hadron (pp / pp̄)",
    "ep": "ep",
    "mumu": "μ⁺μ⁻",
    "nu": "Neutrino",
    "none": "Not collider-specific",
}

# code -> (label, group)
TOPICS = {
    "reco": ("Reconstruction", "Tau performance"),
    "id": ("Identification", "Tau performance"),
    "calib": ("Energy calibration", "Tau performance"),
    "trig": ("Trigger", "Tau performance"),
    "dm": ("Decay-mode classification", "Tau performance"),
    "boost": ("Boosted / di-τ", "Tau performance"),
    "fake": ("Background / fake estimation", "Tau performance"),
    "ml": ("Machine learning", "Methods & tools"),
    "jettag": ("Jet tagging (non-τ)", "Methods & tools"),
    "mass": ("Di-τ mass reconstruction", "Methods & tools"),
    "mc": ("Simulation / MC tools", "Methods & tools"),
    "det": ("Detector / computing / upgrade", "Methods & tools"),
    "sm": ("SM: Z, W, top with τ", "Physics analyses"),
    "higgs": ("Higgs → ττ", "Physics analyses"),
    "bsm": ("BSM searches", "Physics analyses"),
    "pol": ("Polarisation / spin / CP", "Physics analyses"),
    "prop": ("τ properties (BR, lifetime, LFU, LFV)", "Physics analyses"),
    "bphys": ("B decays to τ", "Physics analyses"),
    "nu": ("τ neutrino", "Physics analyses"),
    "theory": ("Theory / phenomenology", "Theory"),
    "review": ("Review / overview", "Context"),
    "history": ("Historical / discovery", "Context"),
    "prospects": ("Prospects / physics programme", "Context"),
}
TOPIC_GROUP_ORDER = ["Tau performance", "Methods & tools", "Physics analyses", "Theory", "Context"]


def doc_type(e):
    rn = e.get("reportnumber", "")
    venue = e.get("journal", "") + " " + e.get("booktitle", "")
    if "TDR" in rn:
        return "Technical design report"
    if e["ENTRYTYPE"] == "techreport":
        if re.search(r"ATLAS-CONF|ATL-PHYS-PUB|CMS-PAS|CMS-DP", rn) or e["ID"].startswith("CMS:DP") \
                or "Performance Summary" in e.get("note", "") or "TauFinder" in e["ID"]:
            return "Public note (CONF / PUB / PAS / DP)"
        return "Preprint"
    if e["ENTRYTYPE"] == "inproceedings" or re.search(r"PROC|-CR-|CONF", rn) or re.search(
            r"PoS|Proc\. Suppl|eConf|AIP Conf|EPJ Web Conf|Phys\. Proc|Conf\. Ser|HiHEP", venue):
        return "Proceedings / talk"
    if re.search(r"Rev\. Mod|Rept|Ann\. Rev|Prog\. Part|Springer Tracts", venue):
        return "Journal (review)"
    return "Journal article"


def link(e):
    if e.get("doi"):
        return "https://doi.org/" + e["doi"]
    if e.get("eprint"):
        return "https://arxiv.org/abs/" + e["eprint"]
    return e.get("url", "")


def short_authors(e):
    coll = e.get("collaboration")
    names = [a.strip() for a in clean(e.get("author", "")).split(" and ") if a.strip()]
    first = names[0].split(",")[0] if names else ""
    if coll and (len(names) > 3 or "others" in names or first.endswith("Collaboration")):
        colls = [c.strip() for c in coll.split(",")]
        if len(colls) > 4:
            colls = colls[:4] + ["others"]
        return ", ".join(colls) + " Collaboration" + ("s" if len(colls) > 1 else "")
    if not names:
        return ""
    if len(names) == 1:
        return first
    if len(names) == 2 and "others" not in names:
        return first + " & " + names[1].split(",")[0]
    return first + " et al."


def venue(e):
    if e.get("journal"):
        s = clean(e["journal"])
        if e.get("volume"):
            s += " " + clean(e["volume"])
        if e.get("pages"):
            s += ", " + clean(e["pages"])
        return s
    if e.get("booktitle"):
        return clean(e["booktitle"])
    return clean(e.get("reportnumber", "").split(",")[0]) or clean(e.get("institution", ""))


def read_classification(path):
    cls = {}
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4:
            raise ValueError(f"{path}:{n}: expected 4 '|'-separated fields")
        key, exps, coll, topics = parts
        split = lambda s: [x.strip() for x in s.split(",") if x.strip()]
        rec = {"exp": split(exps), "coll": coll, "topics": split(topics)}
        for x in rec["exp"]:
            if x not in EXPERIMENTS:
                raise ValueError(f"{path}:{n}: unknown experiment code '{x}'")
        if coll not in COLLISIONS:
            raise ValueError(f"{path}:{n}: unknown collision code '{coll}'")
        for x in rec["topics"]:
            if x not in TOPICS:
                raise ValueError(f"{path}:{n}: unknown topic code '{x}'")
        cls[key] = rec
    return cls


def build_records(entries, cls):
    out = []
    for e in entries:
        c = cls.get(e["ID"], {"exp": [], "coll": "", "topics": []})
        out.append({
            "key": e["ID"],
            "title": clean(e.get("title", "")),
            "authors": short_authors(e),
            "allAuthors": clean(e.get("author", "")),
            "year": int(re.sub(r"\D", "", e.get("year", "0")) or 0),
            "venue": venue(e),
            "report": clean(e.get("reportnumber", "")),
            "url": link(e),
            "doctype": doc_type(e),
            "exp": c["exp"],
            "coll": c["coll"],
            "topics": c["topics"],
            "raw": e["_raw"],
        })
    return out


def zotero_bib(entries, cls):
    """Same .bib with a `keywords` field holding the taxonomy; Zotero imports keywords as tags."""
    chunks = []
    for e in entries:
        c = cls.get(e["ID"])
        raw = e["_raw"]
        if c:
            tags = [f"exp: {EXPERIMENTS[x][0]}" for x in c["exp"]]
            tags += sorted({f"facility: {EXPERIMENTS[x][1]}" for x in c["exp"]})
            tags.append(f"collision: {COLLISIONS[c['coll']]}")
            tags += [f"topic: {TOPICS[t][0]}" for t in c["topics"]]
            tags += sorted({f"area: {TOPICS[t][1]}" for t in c["topics"]})
            tags.append(f"type: {doc_type(e)}")
            kw = ", ".join(t.replace(",", "") for t in tags)
            raw = re.sub(r"\n?\s*\}\s*$", f",\n\tkeywords = {{{kw}}}\n}}", raw.rstrip())
        chunks.append(raw)
    return "\n\n".join(chunks) + "\n"


def read_read(path):
    """read.txt: one bib key per line (# comments allowed)."""
    p = Path(path)
    if not p.exists():
        return []
    return [k for k in (l.split("#", 1)[0].strip() for l in p.read_text().splitlines()) if k]


def write_read(path, keys):
    body = "\n".join(sorted(set(keys)))
    Path(path).write_text("# Papers marked as read (one bib key per line). Written by the viewer; safe to edit.\n"
                          + body + ("\n" if body else ""))


def read_bins(path):
    """bins.txt: `bin name | key1, key2, ... | optional note` per line."""
    p = Path(path)
    if not p.exists():
        return []
    bins = []
    for n, line in enumerate(p.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) not in (2, 3):
            raise ValueError(f"{path}:{n}: expected 'name | keys | note'")
        keys = [k.strip() for k in parts[1].split(",") if k.strip()]
        bins.append({"name": parts[0], "keys": keys, "note": parts[2] if len(parts) == 3 else ""})
    return bins


BINS_HEADER = """# Bins: papers that belong together (e.g. journal paper + PAS/CONF note + proceedings
# of the same study). One bin per line:   name | key1, key2, ... | optional note
# Written by the viewer when you edit bins there; safe to edit by hand.
"""


def write_bins(path, bins):
    clean_field = lambda s: str(s).replace("|", "/").replace("\n", " ").strip()
    lines = []
    for b in sorted(bins, key=lambda b: b["name"].lower()):
        keys = [clean_field(k) for k in b["keys"] if clean_field(k)]
        if len(keys) < 2:
            continue
        line = f"{clean_field(b['name'])} | {', '.join(keys)}"
        if b.get("note"):
            line += f" | {clean_field(b['note'])}"
        lines.append(line)
    Path(path).write_text(BINS_HEADER + "\n" + "\n".join(lines) + "\n")


def make_html(bib, classification, read_path, bins_path):
    """Return (html, entries, cls, warnings)."""
    entries = parse_bib(Path(bib).read_text())
    cls = read_classification(classification)
    keys = {e["ID"] for e in entries}
    warnings = []
    missing = sorted(k for k in keys if k not in cls)
    stale = sorted(k for k in cls if k not in keys)
    if missing:
        warnings.append(f"{len(missing)} unclassified entries: {', '.join(missing)}")
    if stale:
        warnings.append(f"{len(stale)} classified keys not in bib: {', '.join(stale)}")
    bins = read_bins(bins_path)
    unknown = sorted({k for b in bins for k in b["keys"] if k not in keys})
    if unknown:
        warnings.append(f"bins.txt keys not in bib: {', '.join(unknown)}")
    seen, dup = set(), set()
    for b in bins:
        for k in b["keys"]:
            (dup if k in seen else seen).add(k)
    if dup:
        warnings.append(f"keys in more than one bin (last one wins): {', '.join(sorted(dup))}")

    meta = {
        "experiments": {k: {"label": v[0], "facility": v[1]} for k, v in EXPERIMENTS.items()},
        "facilityOrder": FACILITY_ORDER,
        "collisions": COLLISIONS,
        "topics": {k: {"label": v[0], "group": v[1]} for k, v in TOPICS.items()},
        "topicGroupOrder": TOPIC_GROUP_ORDER,
        "source": Path(bib).name,
    }
    cites_path = Path(bib).with_name("citations.json")
    cites = json.loads(cites_path.read_text()) if cites_path.exists() else None
    if cites:
        stale = sorted({k for e in cites["edges"] for k in e[:2]} - keys)
        if stale:
            warnings.append(f"citations.json has keys not in bib (re-run citegraph.py): {', '.join(stale[:10])}")
        unknown = sorted(keys - set(cites["coverage"]))
        if unknown:
            warnings.append(f"{len(unknown)} entries not in citations.json yet (re-run citegraph.py)")
    data = json.dumps({"meta": meta, "papers": build_records(entries, cls),
                       "read": read_read(read_path), "bins": bins, "cites": cites}, ensure_ascii=False)
    data = data.replace("</", "<\\/")
    html = (HERE / "template.html").read_text().replace("/*__DATA__*/null", data)
    return html, entries, cls, warnings


def add_common_args(ap):
    ap.add_argument("bib", nargs="?", default=str(HERE / "tau_reco_merged.bib"))
    ap.add_argument("classification", nargs="?", default=str(HERE / "classification.txt"))
    ap.add_argument("--read-file", default=str(HERE / "read.txt"))
    ap.add_argument("--bins-file", default=str(HERE / "bins.txt"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("-o", "--out", default=str(HERE / "taxonomy.html"))
    ap.add_argument("--zotero-bib", help="also write a .bib with taxonomy tags in `keywords` for Zotero import")
    args = ap.parse_args()

    try:
        html, entries, cls, warnings = make_html(args.bib, args.classification, args.read_file, args.bins_file)
    except ValueError as e:
        sys.exit(f"error: {e}")
    for w in warnings:
        print("warning:", w)
    Path(args.out).write_text(html)
    print(f"wrote {args.out} ({len(entries)} entries)")

    if args.zotero_bib:
        Path(args.zotero_bib).write_text(zotero_bib(entries, cls))
        print(f"wrote {args.zotero_bib}")


if __name__ == "__main__":
    main()
