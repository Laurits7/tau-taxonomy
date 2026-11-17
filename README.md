# tau-taxonomy — tau paper taxonomy browser

A small, dependency-free tool that turns a BibTeX file into a browsable, filterable
"taxonomy tree" of papers (by experiment, collision type, topic, document type and year).

Source bibliography: `tau_reco_merged.bib` (199 entries, copied from `~/Downloads`).

## Quick start

```bash
git clone git@github.com:Laurits7/tau-taxonomy.git && cd tau-taxonomy
./tau_taxonomy
```

This starts the viewer on a local web server (`http://127.0.0.1:8765/`, localhost only)
and opens it in the browser. Stop it with Ctrl-C. Read marks and bins you set in the
page are saved immediately to `read.txt` / `bins.txt`, and reloading the page picks up
any edits to the `.bib`, `classification.txt` or `bins.txt`.

```bash
./tau_taxonomy --no-open                              # start without opening a browser
./tau_taxonomy --port 9000                            # different port
./tau_taxonomy build                                  # only write a static taxonomy.html
./tau_taxonomy build --zotero-bib tau_reco_zotero.bib # also write the Zotero-tagged .bib
```

The static `taxonomy.html` is a single self-contained file you can open or share; it
shows read marks and bins but cannot change them.

To run it from anywhere as just `tau_taxonomy`, link it into a directory on your `PATH`:

```bash
ln -s ~/Projects/paper_analyzer/tau_taxonomy ~/.local/bin/tau_taxonomy
```

Only the Python 3 standard library is needed.

## Using the viewer

- **Filters** (left sidebar), with live counts:
  - **Experiment**, grouped by facility: LHC (ATLAS / CMS / LHCb), Tevatron, SppS,
    LEP / SLC, early e⁺e⁻ (SPEAR / PEP), B factories / τ-charm, HERA,
    future colliders (ILD, CLIC, FCC-ee, muon collider, generic e⁺e⁻),
    neutrino experiments, and **General** (experiment-agnostic).
  - **Collision type**: e⁺e⁻, hadron (pp / pp̄), ep, μ⁺μ⁻, neutrino, not collider-specific.
  - **Topic**, in five areas:
    - *Tau performance*: reconstruction, identification, energy calibration, trigger,
      decay-mode classification, boosted / di-τ, background / fake estimation
    - *Methods & tools*: machine learning, jet tagging (non-τ), di-τ mass reconstruction,
      simulation / MC tools, detector / computing / upgrade
    - *Physics analyses*: SM (Z, W, top), Higgs → ττ, BSM searches,
      polarisation / spin / CP, τ properties, B decays to τ, τ neutrino
    - *Theory / phenomenology*
    - *Context*: review / overview, historical / discovery, prospects
  - Topics can be combined as **any** (at least one) or **all**.
  - **Document type** (journal, review journal, preprint, CONF/PUB/PAS/DP note,
    proceedings, TDR) and **year range**.
  - Within one filter, selections are OR-ed; across filters, they are AND-ed.
- **Grouping**: up to three nested levels (facility, experiment, collision type,
  topic area, topic, document type, decade); papers are sorted newest-first by default.
  A paper with several tags appears in every matching group.
- **Search**: title, authors, bib key, report number, venue, year.
- **Export** the current selection: copy `\cite{…}` with all keys, download `.bib`
  or `.csv`. Each paper has a link (DOI → arXiv → CDS), a click-to-copy key and a
  "bib" toggle showing the raw entry.
- The current view is stored in the URL, so views can be bookmarked.

## Reading status and bins

- **Read marks**: click "mark read" on a paper (read papers get a ✓ and a muted title).
  Filter by *Reading status* in the sidebar. Saved in `read.txt` (one key per line).
- **Bins** group papers that belong together, typically the journal paper, the
  PAS/CONF note and the proceedings of the same study.
  - Tick the checkbox left of several papers, then **Put in bin…** in the bar at
    the bottom. Give a new name or an existing one; if a selected paper is already
    in a bin, that bin is merged in. **Remove from bins** takes papers out
    (a bin with fewer than two papers disappears). The same bar marks papers read/unread.
  - Click a bin chip (⧉) to show only that bin; Shift-click it to edit the bin's note.
  - **Merge bins** (toolbar, on by default) lists each bin once: the journal paper is
    shown in full (otherwise preprint/TDR, then public note, then proceedings; newest
    first), with the other members listed compactly underneath. Members that do not
    match the current filters are dimmed. Grouping uses the main paper's tags.
  - `\cite{…}` and `.bib` export use the listed papers, so with merging on you get
    one key per bin; the `.csv` export always has every matching paper, with
    read/bin columns.
  - Saved in `bins.txt` as `name | key1, key2, ... | note`, which you can also edit by hand.

The pre-filled bins are my reading of the bibliography: notes starting with
"same study" / "companion" are clear-cut (same report number, or a CONF note
superseded by the paper); notes starting with **"guess"** are likely but unverified
and worth checking.

## Citation graph tab

The **Citation graph** tab (top of the page) shows which papers in the collection cite each other,
as a timeline: year left to right, one lane per facility (or topic area, collision type,
document type), colour by topic area (or facility, collision type), marker shape by document
type, marker size by how often the paper is cited within the collection. Hover a paper to
highlight its links, click it to list what it cites and what cites it (with the source of each
link). The sidebar filters apply to the graph too. Below the graph is a list of the papers the
collection cites most often that are not in it yet.

The links are stored in `citations.json`, made by

```bash
python3 citegraph.py          # needs pdftotext (poppler) and internet access
```

It combines two sources:

- **Full text**: each entry is matched to its item in the local Zotero library (`~/Zotero`,
  read-only), the attached PDFs are converted with `pdftotext`, and the text is searched for every
  other entry's arXiv ID, DOI, report number, journal reference or full title.
- **INSPIRE-HEP** reference lists.

PDF-only links are mostly CONF / PAS / DP notes that INSPIRE does not link; INSPIRE-only
links mostly come from entries without a PDF in Zotero. Responses and extracted text are cached
in `.citecache/`; use `--refresh` to re-query INSPIRE. Re-run it after adding papers.

## Editing the categories

All classification lives in `classification.txt`, one line per paper:

```
bibkey | experiments | collision | topics
CMS:2022prd | CMS | had | id, ml
```

- `experiments`, `topics`: comma-separated codes (listed at the top of the file;
  labels and grouping are defined in `build.py` → `EXPERIMENTS`, `TOPICS`).
- `collision`: `ee | had | ep | mumu | nu | none`.
- Reload the page (or start `./tau_taxonomy`) afterwards. Unknown codes are reported as errors.
- New `.bib` entries that are not yet classified appear as **Unclassified** in the
  viewer and are listed as a warning by `build.py`.

Judgement calls worth checking: `Innocente:1992gq` and `Garcia-Abia:1997nda` are
tagged "LEP (generic)"; `Kalinowski:2025vci` is tagged General rather than CMS.

To add a new category, add its code to `EXPERIMENTS` / `TOPICS` in `build.py`
and use it in `classification.txt`.

## Zotero

```bash
./tau_taxonomy build --zotero-bib tau_reco_zotero.bib
```

writes a copy of the bibliography with the taxonomy in each entry's `keywords`
field (e.g. `exp: CMS`, `facility: LHC`, `collision: e⁺e⁻`, `topic: Trigger`,
`area: Tau performance`, `type: Journal article`). Importing it into Zotero
(File → Import) turns these into tags; selecting several tags in the tag selector
narrows to papers that have all of them, and saved searches can reproduce
frequently used views.

## Other options

- `python3 build.py OTHER.bib OTHER_classification.txt -o other.html` builds a
  viewer for a different bibliography.

## Files

| File | Purpose |
|---|---|
| `tau_taxonomy` | Launcher: start the viewer (or `build` a static page) |
| `serve.py` | Local server: rebuilds the page on reload, saves read marks / bins |
| `taxonomy.html` | Static, read-only snapshot of the viewer |
| `classification.txt` | Hand classification of every entry (edit this) |
| `read.txt` | Papers marked as read |
| `bins.txt` | Bins of related papers (same study, companion papers, …) |
| `build.py` | Builds the page and the Zotero-tagged `.bib`; defines the category labels |
| `template.html` | Viewer page (HTML/CSS/JS); the data is injected by `build.py` |
| `bibparse.py` | Minimal BibTeX parser and TeX → Unicode title cleaning |
| `tau_reco_merged.bib` | Source bibliography |
| `tau_reco_zotero.bib` | Generated `.bib` with taxonomy tags, for Zotero import |
| `citegraph.py` | Finds citation links (Zotero PDFs + INSPIRE) and writes `citations.json` |
| `citations.json` | Citation links for the graph tab (generated; safe to commit) |

## Possible extensions

- Create a nested collection tree in a Zotero library via the Zotero web API
  (needs an API key), or build the viewer directly from a Zotero library.
- Co-citation / shared-reference view on top of the citation graph.
