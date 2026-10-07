# Offline linguistic base (OEWN)

Matthew's Step 2 rule: Language meaning uses an offline lexicon on disk.
Runtime never reaches the internet.

## Contents

- `oewn-2024.xml.gz` — Open English WordNet 2024 LMF archive (downloaded once).
- `wn_data/` — local `wn` package database built from that archive.
  - `wn_data/wn.db` is generated locally (often >100MB). Do not rely on GitHub for it;
    bootstrap builds it from `oewn-2024.xml.gz` when missing.

## Bootstrap

```bash
python3 -c "from lexicon.oewn_offline import ensure_oewn; ensure_oewn()"
```

Requires the `wn` package (`pip install wn`). No network at runtime after the archive is present.
