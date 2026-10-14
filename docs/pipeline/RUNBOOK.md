# Runbook: subtitle pipeline (Greek)

Η ροή: βρίσκει υποψήφιους υπότιτλους μιας ταινίας → τους βαθμολογεί και
διαλέγει την καλύτερη πηγή → μεταφράζει στα ελληνικά με δωρεάν LLM →
διορθώνει timing και ταχύτητα ανάγνωσης με ελέγχους → αποφασίζει: skip,
human review ή auto-approve → φτιάχνει την εντολή upload (μόνο dry-run).

Κώδικας: `src/subtitlekit/pipeline/`. Αποφάσεις: `DECISIONS.md`.
Ευρήματα από τα δείγματα: `HEURISTICS.md`. Χάρτης των παλιών projects:
`INVENTORY.md`.

## Πρώτη φορά (μία φορά)

```bash
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline
uv venv -q .venv && uv pip install -q -p .venv/bin/python -e ".[dev]"
docs/pipeline/demo/setup_demo.sh          # φτιάχνει ~/pipeline-demo/films με symlinks
```

Κάθε ταινία είναι ένας φάκελος: όλα τα `.srt` μέσα του είναι υποψήφιοι.
Προαιρετικά: `film.yaml` (title, year, imdb_id, release, fps, synopsis,
cast, `timing_reference`) και `opensubtitles.json` (απάντηση του API v1
search, για τα πεδία `ai_translated`, `from_trusted` κ.λπ.).

## 5 εντολές για το πρωί

1. Δες πώς βαθμολογεί τους υπότιτλους μιας ταινίας (χωρίς LLM, 1 δευτερόλεπτο):

   ```bash
   .venv/bin/subtitlekit pipeline analyze ~/pipeline-demo/films/The.Housemaid.2025
   ```

2. Τρέξε όλη τη ροή γρήγορα σε 60 γραμμές (πραγματικό LLM, ~1 λεπτό· ένα
   partial run πάει πάντα σε human review):

   ```bash
   .venv/bin/subtitlekit pipeline run ~/pipeline-demo/films/Hamnet.2025 --max-cues 60 --out /tmp/pl-try
   open /tmp/pl-try/Hamnet.2025/report.md
   ```

3. Διάβασε τα αποτελέσματα της νύχτας (πλήρεις ταινίες) και την ουρά review:

   ```bash
   open ~/pipeline-demo/out/Hamnet.2025/report.md ~/pipeline-demo/out/The.Housemaid.2025/report.md
   .venv/bin/subtitlekit pipeline queue --out ~/pipeline-demo/out
   ```

4. Δες την εντολή upload που θα έτρεχε (dry-run, ο κωδικός εμφανίζεται ως `***`):

   ```bash
   .venv/bin/subtitlekit pipeline upload ~/pipeline-demo/out/Hamnet.2025
   ```

5. Φτιάξε δικό σου config και τρέξε όλες τις ταινίες ενός φακέλου:

   ```bash
   .venv/bin/subtitlekit pipeline init-config -o ~/pipeline.yaml   # άλλαξε scan.films_dir, thresholds
   .venv/bin/subtitlekit pipeline run --all -c ~/pipeline.yaml
   ```

Χωρίς δίκτυο ή LLM: πρόσθεσε `--mock-llm` (ψεύτικη «μετάφραση» με ελληνικούς
χαρακτήρες, μόνο για να δεις τη ροή) ή `--no-llm`.

## Τι κάνει κάθε στάδιο

| Στάδιο | Τι ελέγχει / αλλάζει | Αν αποτύχει |
|---|---|---|
| analyze | CPS (p50/p90/p95), γραμμές > 42, overlaps, μικρά κενά, διάρκειες, frame-snapping, timestamps σε 10 ms, credits, 1:1 αντιγραφή timing από αγγλικά χωρίς συμπύκνωση → professional / amateur / machine | — |
| worth-it | υπάρχει επαγγελματικός ελληνικός; υπάρχει δικός σου (`haroldpoi`); η πηγή είναι professional με score ≥ 50; release όχι CAM/TS | `skip` με λόγους, καμία κλήση LLM |
| translate | chunks των 40 γραμμών σε JSON, ταινία + ονόματα ως context· το timing δεν περνά από το LLM | οι γραμμές μένουν αμετάφραστες → human review |
| fixes | resync (αν δοθεί `timing_reference`), overlaps, κενό ≥ 2 frames, επέκταση διάρκειας προς 17 CPS, αναδίπλωση ≤ 42, συμπύκνωση με LLM όσων μένουν > 20 CPS | κάθε στάδιο ελέγχεται· αν σπάσει κάτι, γυρίζει πίσω |
| validators | ίδιος αριθμός και σειρά, χωρίς overlaps, θετικές διάρκειες· κάθε συμπυκνωμένη γραμμή: ίδιοι αριθμοί, ονόματα, άρνηση, ερώτηση + έλεγχος νοήματος από το LLM | η γραμμή επιστρέφει στο πριν και μπαίνει flag |
| route | auto_approve μόνο αν όλα περνούν, 0 αμετάφραστα, flags ≤ 2 %, ≤ 1 % πάνω από 25 CPS | `review_queue/<film>.json` |
| upload | φτιάχνει την ακριβή εντολή `upload_cli` του opensubtitles-go | πάντα dry-run απόψε |

## Αποτελέσματα demo (νύχτα 2026-10-14)

Δες την ενότητα «Demo results» στο τέλος του `DECISIONS.md` και τα
`~/pipeline-demo/out/*/report.md`.

## Ανοιχτές αποφάσεις για σένα

1. **Πραγματικό upload.** Πότε επιτρέπεται; Πρόταση: μόνο μετά από δική σου
   έγκριση ανά ταινία, για τις πρώτες 10 ταινίες. Χρειάζονται και τα τρία:
   `upload.allow_real_upload: true`, `--really-upload`, `OS_USERNAME` /
   `OS_PASSWORD` στο περιβάλλον. Σημείωση: το upload_cli παίρνει τον κωδικό
   ως όρισμα, άρα φαίνεται στη λίστα διεργασιών όσο τρέχει.
2. **Σήμανση AI.** Το `-auto` (automatic translation) μπαίνει από default.
   Θέλεις να το κρατήσεις και μετά από δική σου επιμέλεια;
3. **Όρια.** `cps_limit` 17, συμπύκνωση πάνω από 20 CPS, flags ≤ 2 %,
   `min_source_score` 50. Τα 17/20 είναι συντηρητικά για ελληνικά· οι
   ελληνικοί επαγγελματικοί υπότιτλοι των δειγμάτων έχουν p95 16–20.
4. **Αυτόματη ενεργοποίηση.** Απόψε μόνο χειροκίνητα. Για cron: πρόταση
   `0 3 * * * cd <repo> && .venv/bin/subtitlekit pipeline run --all -c ~/pipeline.yaml`.
   Από πού έρχονται οι ταινίες (subs4free scrape, η λίστα «translated
   soon.csv», OpenSubtitles discover); χρειάζεται API key του OpenSubtitles.
5. **Πηγή όταν δεν υπάρχει αγγλικός.** Σήμερα μεταφράζει μόνο από
   professional πηγή. Θέλεις να επιτρέπεται και amateur (π.χ. Avatar: μόνο
   δανέζικος TS) με υποχρεωτικό human review;
6. **Έλεγχος νοήματος.** Σήμερα μόνο κανόνες + LLM. Ένα τοπικό embedding
   μοντέλο (π.χ. multilingual) θα έδινε δεύτερη γνώμη χωρίς κόστος· θέλεις;
