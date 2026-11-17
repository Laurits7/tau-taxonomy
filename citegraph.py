#!/usr/bin/env python3
"""Find which papers in the bibliography cite which, and write citations.json for the viewer's graph tab.

Two sources, combined:
  1. Full text: each entry is matched to its item in the local Zotero library, the attached PDFs are
     converted with `pdftotext`, and the text is searched for every other entry's arXiv ID, DOI,
     report number, journal reference (volume + first page) or full title.
  2. INSPIRE-HEP: the entry's reference list (by texkey, arXiv ID, DOI, report number or title).

A link found only in the full text is dropped if the cited paper is more than a year newer than the
citing one (that happens when near-identical note titles are confused).
Also lists the papers cited most often by the collection that are not in it (from INSPIRE).

Usage:  python3 citegraph.py [bibfile] [--zotero ~/Zotero] [-o citations.json] [--refresh]
Needs `pdftotext` (poppler) and network access to inspirehep.net; responses are cached in .citecache/.
"""
import argparse
import difflib
import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from bibparse import clean, parse_bib

HERE = Path(__file__).parent
CACHE = HERE / ".citecache"
GREEK = {"τ": "tau", "ν": "nu", "μ": "mu", "π": "pi", "γ": "gamma", "ρ": "rho", "α": "alpha", "→": "to", "±": "pm"}


def norm(t):
    t = clean(t or "").lower()
    for k, v in GREEK.items():
        t = t.replace(k, v)
    return re.sub(r"[^a-z0-9]", "", t)


def year(e):
    return int(re.sub(r"\D", "", e.get("year", "0"))[:4] or 0)


# ---------------- INSPIRE ----------------
class Inspire:
    FIELDS = ("fields=control_number,titles.title,texkeys,references.record,arxiv_eprints.value,dois.value,"
              "report_numbers.value,earliest_date")

    def __init__(self, refresh):
        self.path = CACHE / "inspire.json"
        self.cache = {} if refresh or not self.path.exists() else json.loads(self.path.read_text())

    def get(self, url):
        if url in self.cache:
            return self.cache[url]
        r = None
        for i in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "tau-taxonomy-citegraph/1.0"})
                r = json.load(urllib.request.urlopen(req, timeout=40))
                break
            except Exception as ex:  # rate limit / network hiccup
                print(f"  retry ({ex})", file=sys.stderr)
                time.sleep(3 * (i + 1))
        self.cache[url] = r
        self.path.write_text(json.dumps(self.cache))
        time.sleep(0.35)
        return r

    def search(self, q, size=1, fields=None):
        r = self.get(f"https://inspirehep.net/api/literature?size={size}&{fields or self.FIELDS}&q="
                     + urllib.parse.quote(q))
        return [h["metadata"] for h in (r or {}).get("hits", {}).get("hits", [])]

    def find(self, e):
        tries = [f'texkey:"{e["ID"]}"']
        if e.get("eprint"):
            tries.append("arxiv:" + e["eprint"])
        if e.get("doi"):
            tries.append(f'doi:"{e["doi"]}"')
        if e.get("reportnumber"):
            tries.append(f'r "{e["reportnumber"].split(",")[0].strip()}"')
        for q in tries:
            hits = self.search(q)
            if hits:
                return hits[0]
        if e.get("title"):
            hits = self.search(f't "{clean(e["title"])[:150]}"')
            if hits and norm(hits[0]["titles"][0]["title"])[:40] == norm(e["title"])[:40]:
                return hits[0]
        return None


# ---------------- Zotero ----------------
def zotero_texts(entries, zdir, inspire_meta):
    """Map bib key -> list of text files extracted from the PDFs attached to its Zotero item."""
    db = sqlite3.connect(f"file:{zdir / 'zotero.sqlite'}?immutable=1", uri=True)
    items = {}
    for iid, f, v in db.execute(
            "select i.itemID, f.fieldName, v.value from items i join itemData d using(itemID) join fields f using(fieldID)"
            " join itemDataValues v using(valueID) where f.fieldName in ('title','DOI','url','extra','archiveID')"):
        items.setdefault(iid, {})[f] = v
    pdfs = {}
    for parent, key in db.execute("select a.parentItemID, i.key from itemAttachments a join items i on i.itemID=a.itemID"
                                  " where a.parentItemID is not null"):
        pdfs.setdefault(parent, []).extend(glob.glob(str(zdir / "storage" / key / "*.pdf")))
    pdfs = {k: v for k, v in pdfs.items() if v}
    by_doi, by_arxiv, by_title = {}, {}, {}
    for iid in pdfs:
        d = items.get(iid, {})
        if d.get("DOI"):
            by_doi[d["DOI"].lower()] = iid
        for s in (d.get("archiveID"), d.get("extra"), d.get("url")):
            m = re.search(r"arxiv[^\d]{0,12}(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})", s or "", re.I)
            if m:
                by_arxiv[m.group(1)] = iid
        if d.get("title"):
            by_title[norm(d["title"])[:80]] = iid
    out = {}
    (CACHE / "txt").mkdir(parents=True, exist_ok=True)
    for e in entries:
        m = inspire_meta.get(e["ID"], {})
        dois = [e.get("doi", "")] + [x["value"] for x in m.get("dois", [])]
        arxs = [e.get("eprint", "")] + [x["value"] for x in m.get("arxiv_eprints", [])]
        iid = next((by_doi[d.lower()] for d in dois if d and d.lower() in by_doi), None) \
            or next((by_arxiv[a] for a in arxs if a in by_arxiv), None)
        t = norm(e.get("title"))[:80]
        if not iid and t:
            iid = by_title.get(t)
            if not iid:
                best = max(by_title, key=lambda k: difflib.SequenceMatcher(None, t, k).ratio())
                if difflib.SequenceMatcher(None, t, best).ratio() > 0.85:
                    iid = by_title[best]
        if not iid:
            continue
        files = []
        for pdf in pdfs[iid]:
            txt = CACHE / "txt" / (hashlib.md5(pdf.encode()).hexdigest() + ".txt")
            if not txt.exists():
                subprocess.run(["pdftotext", "-q", pdf, str(txt)], timeout=180, check=False)
            if txt.exists() and txt.stat().st_size > 500:
                files.append(txt)
        if files:
            out[e["ID"]] = files
    return out


# ---------------- full-text matching ----------------
def identifiers(e, m):
    arx = {e.get("eprint", "")} | {x["value"] for x in m.get("arxiv_eprints", [])}
    dois = {e.get("doi", "").lower()} | {x["value"].lower() for x in m.get("dois", [])}
    reps = {r.strip() for r in clean(e.get("reportnumber", "")).split(",")} | {x["value"] for x in m.get("report_numbers", [])}
    reps = {re.sub(r"[^A-Z0-9]", "", r.upper()) for r in reps
            if re.search(r"(PAS|CONF|PUB|DP|NOTE|TDR|EP|PH|PPE|ACC|LHCC)-", r) and len(r) > 8}
    jr = None
    if e.get("volume") and e.get("pages"):
        pg = re.split(r"[-–]", clean(e["pages"]))[0].strip()
        if len(re.sub(r"\D", "", pg)) >= 3:
            jr = re.compile(r"(?<![\d.])" + re.escape(clean(e["volume"]).strip()) + r"(?!\d)[^\n]{0,30}?(?<![\d.])"
                            + re.escape(pg) + r"(?!\d)")
    t = norm(e.get("title"))[:100]
    return {"arx": [re.compile(r"(?<![\d.])" + re.escape(a) + r"(?!\d)") for a in arx if a],
            "dois": [d for d in dois if d], "reps": reps, "jr": jr, "title": t if len(t) >= 28 else None}


def text_links(texts, ids):
    links = {}
    for a, files in texts.items():
        txt = "\n".join(f.read_text(errors="ignore") for f in files)
        squeezed, low, ntxt = re.sub(r"\s+", "", txt), txt.lower(), norm(txt)
        up = re.sub(r"[^A-Z0-9]", "", txt.upper())
        found = {}
        for b, d in ids.items():
            if b == a:
                continue
            if any(r.search(squeezed) for r in d["arx"]):
                found[b] = "arXiv ID"
            elif any(x in low for x in d["dois"]):
                found[b] = "DOI"
            elif any(x in up for x in d["reps"]):
                found[b] = "report number"
            elif d["title"] and d["title"] in ntxt and d["title"] != ids[a]["title"]:
                found[b] = "title"
            elif d["jr"] and d["jr"].search(txt):
                found[b] = "journal ref"
        links[a] = found
    return links


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bib", nargs="?", default=str(HERE / "tau_reco_merged.bib"))
    ap.add_argument("--zotero", default=os.path.expanduser("~/Zotero"))
    ap.add_argument("-o", "--out", default=str(HERE / "citations.json"))
    ap.add_argument("--refresh", action="store_true", help="ignore cached INSPIRE responses")
    ap.add_argument("--missing", type=int, default=40, help="how many most-cited missing papers to list")
    args = ap.parse_args()
    CACHE.mkdir(exist_ok=True)

    entries = parse_bib(Path(args.bib).read_text())
    by_key = {e["ID"]: e for e in entries}
    ins = Inspire(args.refresh)
    print(f"INSPIRE: looking up {len(entries)} entries…")
    meta = {}
    for e in entries:
        md = ins.find(e)
        if md:
            meta[e["ID"]] = md
    recid = {k: m["control_number"] for k, m in meta.items()}
    key_of = {v: k for k, v in recid.items()}

    print("Zotero: matching entries and extracting PDF text…")
    texts = zotero_texts(entries, Path(args.zotero), meta)
    ids = {e["ID"]: identifiers(e, meta.get(e["ID"], {})) for e in entries}
    print(f"Full text: searching {len(texts)} papers…")
    tl = text_links(texts, ids)

    edges = {}
    for a, found in tl.items():
        for b, how in found.items():
            if year(by_key[b]) > year(by_key[a]) + 1:
                continue
            edges[(a, b)] = {"text": how}
    for a, m in meta.items():
        for r in m.get("references", []):
            rid = int(r.get("record", {}).get("$ref", "/0").rsplit("/", 1)[1])
            b = key_of.get(rid)
            if b and b != a:
                edges.setdefault((a, b), {})["inspire"] = True

    # most-cited papers outside the collection
    outside = Counter()
    for k, m in meta.items():
        for rid in {int(r["record"]["$ref"].rsplit("/", 1)[1]) for r in m.get("references", []) if "record" in r}:
            if rid not in key_of:
                outside[rid] += 1
    top = outside.most_common(args.missing)
    info = {}
    for i in range(0, len(top), 20):
        chunk = [rid for rid, _ in top[i:i + 20]]
        for md in ins.search(" or ".join(f"recid:{r}" for r in chunk), size=20,
                             fields="fields=control_number,titles.title,texkeys,earliest_date,collaborations.value,authors.full_name"):
            info[md["control_number"]] = md
    missing = []
    for rid, n in top:
        md = info.get(rid, {})
        who = (md.get("collaborations") or [{}])[0].get("value") or \
            ((md.get("authors") or [{}])[0].get("full_name", "").split(",")[0])
        missing.append({"recid": rid, "count": n, "title": (md.get("titles") or [{}])[0].get("title", ""),
                        "texkey": (md.get("texkeys") or [""])[0], "year": (md.get("earliest_date") or "")[:4], "who": who})

    coverage = {e["ID"]: ("pdf+inspire" if e["ID"] in texts and meta.get(e["ID"], {}).get("references")
                          else "pdf" if e["ID"] in texts
                          else "inspire" if meta.get(e["ID"], {}).get("references") else "none") for e in entries}
    out = {"edges": [[a, b, v.get("text", ""), bool(v.get("inspire"))] for (a, b), v in sorted(edges.items())],
           "coverage": coverage, "missing": missing,
           "generated": time.strftime("%Y-%m-%d")}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=0))
    both = sum(1 for v in edges.values() if v.get("text") and v.get("inspire"))
    print(f"wrote {args.out}: {len(edges)} links ({both} in both sources, "
          f"{sum(1 for v in edges.values() if not v.get('inspire'))} full text only, "
          f"{sum(1 for v in edges.values() if not v.get('text'))} INSPIRE only)")
    print("coverage:", dict(Counter(coverage.values())))


if __name__ == "__main__":
    main()
