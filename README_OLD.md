# Subtitle Processing Tools

Εργαλεία Python για επεξεργασία και διόρθωση υποτίτλων.

## Εγκατάσταση

```bash
# Δημιουργία virtual environment
python3 -m venv venv
source venv/bin/activate

# Εγκατάσταση dependencies
pip install -r requirements.txt
```

## Εργαλεία

### 1. JSON Generation για LLM Translation

Δημιουργεί JSON από SRT αρχεία για επεξεργασία με LLM.

**Χρήση:**
```bash
python main.py --original original.srt --helper helpful.srt --output output.json
```

**Παράμετροι:**
- `--original`: Αρχείο υπότιτλου για μετάφραση
- `--helper`: Βοηθητικό αρχείο υπότιτλου (άλλη γλώσσα)
- `--output`: Αρχείο εξόδου JSON
- `--skip-sync`: Παράλειψη συγχρονισμού με ffsubsync (αν είναι ήδη συγχρονισμένο)

**JSON Format:**
```json
{
  "id": 16,
  "t": "00:02:28,050 --> 00:02:29,385",
  "trans": "<i>-Det gör jag.</i>\n-Det verkar som...",
  "h": "Parece que está fazendo\no oposto do seu trabalho,"
}
```

---

### 2. Smart Overlap Detection and Correction

Ανιχνεύει και διορθώνει timing προβλήματα στους υποτίτλους.

**Τι διορθώνει:**
- ✅ Overlapping timings (end_time > next_start_time)
- ✅ Χρονολογικά προβλήματα (start <= previous_end)
- ✅ Unreasonable durations (> 60 δευτ., π.χ. typos με ώρες)
- ✅ Duplicate timings

**Χρήση:**
```bash
python fix_overlaps.py \
  --input greek.srt \
  --reference original.srt \
  --output greek_fixed.srt \
  --window 10
```

**Παράμετροι:**
- `--input`: Αρχείο υπότιτλου με προβλήματα
- `--reference`: Reference αρχείο με σωστά timings
- `--output`: Αρχείο εξόδου
- `--window`: Context window για matching (default: 5)
- `--preprocess`: Καθαρίζει το input αρχείο πρώτα (markdown, duplicates κλπ)

**Πώς λειτουργεί:**
1. **Ανίχνευση**: Βρίσκει overlaps, chronological issues, unreasonable durations
2. **Matching**: Ταιριάζει προβληματικές γραμμές με το reference (timing-based)
3. **Διόρθωση**: Αντικαθιστά μόνο τα λάθος timings
4. **Deduplication**: Αφαιρεί duplicate timings
5. **Validation**: Επαληθεύει ότι δεν υπάρχουν προβλήματα

**Αποτελέσματα:**
```
Problems found: 12
Problems fixed: 12
Duplicates removed: 1

Validation:
  no_overlaps: ✓ PASS
  chronological_order: ✓ PASS
  no_duplicates: ✓ PASS
```

---

### 3. Text Corrections with JSON

Εφαρμόζει διορθώσεις κειμένου από JSON αρχείο σε SRT.

**Τι διορθώνει:**
- ✅ Λεξιλόγιο και φυσικότητα
- ✅ Αργκό και ιδιωματισμούς
- ✅ Ροή και σύνταξη
- ✅ Γραμματική και συστολές

**Χρήση:**
```bash
python apply_corrections_FIXED.py
```

**Input Files:**
- `greek_fixed.srt`: Το SRT αρχείο που θέλουμε να διορθώσουμε
- `corrections.json`: JSON με τις διορθώσεις

**JSON Format:**
```json
{
  "id": 43,
  "rx": "δεν έβρισκες στο Λύκειο.",
  "sb": "Στο σχολείο στέγνωνες.",
  "rate": 8,
  "type": "αργκό"
}
```

**Πώς λειτουργεί:**
1. **Global Search**: Αναζητά το `rx` (search text) σε όλα τα subtitles
2. **Smart Matching**: Δοκιμάζει exact, normalized και newline variants
3. **Apply**: Αντικαθιστά με το `sb` (replacement text)
4. **Report**: Αναφέρει ποιες διορθώσεις εφαρμόστηκαν

**Output:**
- `corrected_greek_fixed_FINAL.srt`: Το διορθωμένο αρχείο
- Console report με applied/not found corrections

**Αποτελέσματα:**
```
✓ ID 43 → Applied at subtitle #42 (offset: -2)
✓ ID 62 → Applied at subtitle #60 (offset: -2)
✗ ID 99: NOT FOUND

SUMMARY
Total corrections: 79
✓ Applied: 76
✗ Not found: 3
```

## Δομή Αρχείων

```
submerge/
├── main.py                      # JSON generation για LLM
├── subsync_matcher.py           # Subtitle matching engine
├── fix_overlaps.py              # Smart overlap correction 🆕
├── apply_corrections_FIXED.py   # Text corrections από JSON 🆕
├── encoding_utils.py            # Robust encoding detection
├── srt_preprocessor.py          # SRT cleaning utilities
├── enhanced_matcher.py          # Advanced matching algorithms
├── corrections.ipynb            # Notebook για corrections (Google Colab)
├── corrections.json             # Διορθώσεις κειμένου
├── test_fix_overlaps.py         # Tests για overlap correction
├── test_subsync_matcher.py      # Tests για matching
├── test_enhanced_matcher.py     # Tests για enhanced matching
├── llm_prompt_greek.md          # Οδηγίες για LLM
├── llm_srt_reading_guide.md     # Guide για reading SRT με notes
├── LLM_USAGE_EXAMPLE.md         # Παραδείγματα χρήσης
├── FIX_TIMINGS_GUIDE.md         # Guide για timing correction
└── requirements.txt             # Dependencies
```

## Requirements

```bash
pip install -r requirements.txt
```

**Dependencies:**
- `pysrt>=1.1.2` - SRT parsing
- `pytest>=7.0.0` - Testing
- `ffsubsync>=0.4.0` - Automatic timing sync (optional για main.py)
- `chardet>=5.0.0` - Encoding detection

## Testing

```bash
# Τρέξε όλα τα tests
pytest -v

# Μόνο overlap correction tests
pytest test_fix_overlaps.py -v

# Μόνο matching tests
pytest test_subsync_matcher.py -v
```

## Workflows

### Workflow 1: LLM Translation
```bash
# 1. Generate JSON
python main.py --original original.srt --helper helpful.srt --output for_llm.json --skip-sync

# 2. Send to LLM για μετάφραση (δες llm_prompt_greek.md)

# 3. Αν υπάρχουν timing issues στο output, χρησιμοποίησε fix_overlaps.py
```

### Workflow 2: Fix Timing Issues
```bash
# Διόρθωση overlaps και timing προβλημάτων
python fix_overlaps.py --input greek.srt --reference original.srt --output greek_fixed.srt
```

### Workflow 3: Apply Text Corrections
```bash
# Εφαρμογή διορθώσεων κειμένου από JSON
python apply_corrections_FIXED.py

# Input: greek_fixed.srt + corrections.json
# Output: corrected_greek_fixed_FINAL.srt
```

### Complete Pipeline
```bash
# 1. Generate JSON για LLM
python main.py --original original.srt --helper helpful.srt --output for_llm.json

# 2. LLM μετάφραση → greek.srt

# 3. Fix timing issues
python fix_overlaps.py --input greek.srt --reference original.srt --output greek_fixed.srt

# 4. Apply text corrections
python apply_corrections_FIXED.py
# → corrected_greek_fixed_FINAL.srt
```

## Σημειώσεις

- Το matching χρησιμοποιεί **temporal overlap** για ακρίβεια
- Το fix_overlaps.py δουλεύει με **διαφορετικές γλώσσες** (timing-based matching)
- Το apply_corrections_FIXED.py κάνει **global text search** (δεν βασίζεται σε IDs)
- **Δεν** χρειάζεται sorting - διατηρεί την αρχική σειρά
- Η **αρίθμηση γραμμών** δεν έχει σημασία για τα media players
