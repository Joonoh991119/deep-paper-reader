"""Sprint 10 research-background bulk ingest.

Runs the full ingest pipeline on a curated list of papers drawn from J's
Zotero collections (Efficient Coding, Time Estimation, Magnitude,
Perceptual Bias). Idempotent — re-running only re-embeds chunks that
were missed on the previous pass.

Notion pages are handled via `src.text_ingest.ingest_text` on the
caller side (pages are fetched through the Notion MCP and passed in as
plain-text blobs), so this script is Zotero-only.

Run from the repo root:
    source ~/Documents/Claude/Projects/_mcp-bundle/.env.master
    PYTHONPATH=. .venv/bin/python scripts/sprint10_bulk_ingest.py
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from src import ingest


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sprint10-bulk")


# (zotero_key, pdf_path, doi)
# Curated from 4 priority JOONOH collections. Only papers with a local
# PDF attachment — HTML snapshots skipped.
PAPERS: list[tuple[str, str, str | None]] = [
    # --- Efficient Coding (FIMEVXKF) ---
    ("SU2DU92P", "/Users/joonoh/Zotero/storage/5FLPCFVK/Loh and Bartulovic - 2014 - Efﬁcient Coding Hypothesis and an Introduction to Information Theory.pdf", None),
    ("EDCYGU7P", "/Users/joonoh/Zotero/storage/47RSXPAF/Wei and Stocker - 2016 - Mutual Information, Fisher Information, and Efficient Coding.pdf", "10.1162/NECO_a_00804"),
    ("A5UUMF7X", "/Users/joonoh/Zotero/storage/BEI3YGUA/Prat-Carrabin and Woodford - 2020 - Efficient coding of numbers explains decision bias and noise.pdf", "10.1101/2020.02.18.942938"),
    ("2SX4UP9T", "/Users/joonoh/Zotero/storage/2XFM2HQB/Noise characteristics and prior expectations in human visual speed perception  Nature Neuroscience.pdf", None),
    ("YH3B2Q5T", "/Users/joonoh/Zotero/storage/F3UUDJ2N/Girshick et al. - 2011 - Cardinal rules visual orientation perception reflects knowledge of environmental statistics.pdf", "10.1038/nn.2831"),
    ("9CBJBFXM", "/Users/joonoh/Zotero/storage/MTLGYIYF/Prat-Carrabin and Gershman - 2025 - Bayesian estimation yields anti-Weber variability.pdf", "10.1093/pnasnexus/pgaf275"),
    ("FBYTXBCK", "/Users/joonoh/Zotero/storage/WHYLDBH9/Wei and Stocker - 2015 - A Bayesian observer model constrained by efficient coding can explain 'anti-Bayesian' percepts.pdf", "10.1038/nn.4105"),
    ("Z45WPP5R", "/Users/joonoh/Zotero/storage/4CP3ENQ5/Bhui et al. - 2021 - Resource-rational decision making.pdf", "10.1016/j.cobeha.2021.02.015"),

    # --- Time Estimation (PT9VE66T) ---
    ("N7A3I5IE", "/Users/joonoh/Zotero/storage/NJLLRSMQ/Bliss et al. - 2017 - Serial dependence is absent at the time of perception but increases in visual working memory.pdf", "10.1038/s41598-017-15199-7"),
    ("7IJ4KY7F", "/Users/joonoh/Zotero/storage/PSTHPHA7/Paton and Buonomano - 2018 - The Neural Basis of Timing Distributed Mechanisms for Diverse Functions.pdf", "10.1016/j.neuron.2018.03.045"),
    ("BF6SRMH8", "/Users/joonoh/Zotero/storage/V7IL8JHC/Logarithmic encoding of ensemble time intervals  Scientific Reports.pdf", None),
    ("YV9J5XUQ", "/Users/joonoh/Zotero/storage/HA54SHCV/Wiener et al. - 2014 - Continuous Carryover of Temporal Context Dissociates Response Bias from Perceptual Influence for Dur.pdf", "10.1371/journal.pone.0100803"),
    ("P5ZLTVV8", "/Users/joonoh/Zotero/storage/3QFTD64U/Griffiths and Tenenbaum - 2006 - Optimal Predictions in Everyday Cognition.pdf", "10.1111/j.1467-9280.2006.01780.x"),
    ("EMKNV2QZ", "/Users/joonoh/Zotero/storage/76VVJ34D/Tenenbaum et al. - 2006 - Theory-based Bayesian models of inductive learning and reasoning.pdf", "10.1016/j.tics.2006.05.009"),
    ("K7A2DMT7", "/Users/joonoh/Zotero/storage/3DRT7BJQ/Temporal Processing Neural Correlates and Clinical Relevance.pdf", "10.1176/appi.neuropsych.19120342"),
    ("PCS45SP6", "/Users/joonoh/Zotero/storage/DMCC2VJY/Cheng 등 - 2024 - The impact of task measurements on sequential dependence a comparison between temporal reproduction.pdf", "10.1007/s00426-024-02023-x"),
    ("TG37WI7T", "/Users/joonoh/Zotero/storage/H4MQYIC4/Iterative Bayesian Estimation as an Explanation for Range and Regression Effects A Study on Human P.pdf", None),
    ("CXMDVMKR", "/Users/joonoh/Zotero/storage/F9RNMKH3/Sohn and Lee - 2013 - Dichotomy in perceptual learning of interval timing calibration of mean accuracy and precision diff.pdf", "10.1152/jn.01201.2011"),
    ("AUE72R54", "/Users/joonoh/Zotero/storage/EECH87V2/Jazayeri and Shadlen - 2010 - Temporal context calibrates interval timing.pdf", "10.1038/nn.2590"),

    # --- Magnitude (RE3HBQ58) ---
    ("R6VP37U4", "/Users/joonoh/Zotero/storage/FME5CXS9/Flesch et al. - 2022 - Orthogonal representations for robust context-dependent task performance in brains and neural networ.pdf", "10.1016/j.neuron.2022.01.005"),
    ("UVG8IYYV", "/Users/joonoh/Zotero/storage/LXGTQIVZ/Kim et al. - 2021 - Visual number sense in untrained deep neural networks.pdf", "10.1126/sciadv.abd6127"),
    ("PMWMKBZX", "/Users/joonoh/Zotero/storage/S64J4PZK/Park and Huber - 2022 - A visual sense of number emerges from divisive normalization in a simple center-surround convolution.pdf", "10.7554/eLife.80990"),
    ("288QDPU2", "/Users/joonoh/Zotero/storage/HMRRUJED/Grasso et al. - 2025 - Color-selective numerosity adaptation depends on the automatic categorization of colored information.pdf", "10.1016/j.isci.2025.112572"),
    ("JRUCAREE", "/Users/joonoh/Zotero/storage/LJN5699E/Amit et al. - 2012 - Do object-category selective regions in the ventral visual stream represent perceived distance infor.pdf", "10.1016/j.bandc.2012.06.006"),
    ("PLGHG9VG", "/Users/joonoh/Zotero/storage/2QWPJ3BP/Piazza et al. - 2007 - A Magnitude Code Common to Numerosities and Number Symbols in Human Intraparietal Cortex.pdf", "10.1016/j.neuron.2006.11.022"),
    ("C54TNIMM", "/Users/joonoh/Zotero/storage/853TYBVM/Pooresmaeili et al. - 2013 - Blood Oxygen Level-Dependent Activation of the Primary Visual Cortex Predicts Size Adaptation Illusi.pdf", "10.1523/JNEUROSCI.1770-13.2013"),
    ("USD5DT6P", "/Users/joonoh/Zotero/storage/R8YN8YTE/Collins et al. - 2017 - Numerosity representation is encoded in human subcortex.pdf", "10.1073/pnas.1613982114"),

    # --- Perceptual Bias (SITNFBAX) ---
    ("K3LACFBF", "/Users/joonoh/Zotero/storage/4FW7BJBL/Ceylan and Pascucci - 2023 - Attractive and repulsive serial dependence The role of task relevance, the passage of time, and the.pdf", "10.1167/jov.23.6.8"),
    ("KXXKC4B3", "/Users/joonoh/Zotero/storage/5WAEWWES/Can and Collins - 2025 - Attractive and repulsive history effects in categorical and continuous estimates of orientation perc.pdf", "10.1101/2025.04.24.650437"),
    ("N8Q9UDEJ", "/Users/joonoh/Zotero/storage/7LHH9FJU/Cicchini et al. - 2018 - The functional role of serial dependence.pdf", "10.1098/rspb.2018.1722"),
    ("FW8C8TDJ", "/Users/joonoh/Zotero/storage/GTCI4E4T/Li et al. - 2026 - Reversed effects of prior choices in cross-modal temporal decisions.pdf", "10.1016/j.cognition.2025.106294"),
    ("2TA69EQN", "/Users/joonoh/Zotero/storage/B8I3ALQY/Wiese and Wenderoth - 2008 - What is the Reference in Reference Repulsion.pdf", "10.1068/p5863"),
    ("M3LKPHHV", "/Users/joonoh/Zotero/storage/LFSD7PD7/Park - 2025 - Process dynamics of serial biases in visual perception and working memory processes.pdf", "10.3758/s13423-025-02714-5"),
    ("XEFAXWV9", "/Users/joonoh/Zotero/storage/RKKJAUM7/Lange et al. - 2021 - A confirmation bias in perceptual decision-making due to hierarchical approximate inference.pdf", "10.1371/journal.pcbi.1009517"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip items whose zotero_key already has >0 embeddings in the DB.")
    parser.add_argument("--max", type=int, default=None,
                        help="Cap the number of items for dry runs.")
    args = parser.parse_args()

    total = len(PAPERS)
    if args.max:
        items = PAPERS[: args.max]
    else:
        items = PAPERS

    # Filter to only papers whose PDFs exist.
    missing = [(k, p) for k, p, _ in items if not Path(p).exists()]
    for k, p in missing:
        log.warning("PDF missing for %s: %s", k, p)
    items = [t for t in items if Path(t[1]).exists()]

    if args.skip_existing:
        from src import db as _db
        with _db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.zotero_key
                      FROM papers p
                      JOIN paper_chunks pc ON pc.paper_id = p.id
                      JOIN paper_embeddings pe ON pe.chunk_id = pc.id
                     WHERE p.zotero_key = ANY(%s)
                     GROUP BY p.zotero_key
                    HAVING COUNT(*) > 0
                    """,
                    ([k for k, _, _ in items],),
                )
                existing = {r["zotero_key"] for r in cur.fetchall()}
        items = [t for t in items if t[0] not in existing]
        log.info("skip-existing: %d already embedded, %d to process", len(existing), len(items))

    ok = 0
    fail = 0
    for i, (key, pdf, doi) in enumerate(items, 1):
        t0 = time.time()
        try:
            paper_id = ingest.ingest_pdf(pdf, zotero_key=key, doi=doi)
            dt = time.time() - t0
            log.info("[%d/%d] %s ingested in %.1fs → %s", i, len(items), key, dt, paper_id)
            ok += 1
        except Exception as e:
            log.error("[%d/%d] %s FAILED: %s", i, len(items), key, e)
            fail += 1

    log.info("Done. ok=%d fail=%d total_pool=%d", ok, fail, total)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
