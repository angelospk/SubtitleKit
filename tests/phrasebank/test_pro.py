from subtitlekit.phrasebank.pro import score_greek
from subtitlekit.pipeline.srt import Cue


def body(n=60, start=10_000, frame=None):
    cues, t = [], start
    for i in range(n):
        s, e = t, t + 2000
        if frame:
            s = round(round(s / frame) * frame)
            e = round(round(e / frame) * frame)
        cues.append(Cue(i + 1, s, e, f"Γεια σου, τι κάνεις σήμερα {i};"))
        t += 3137
    return cues


def with_edges(cues, head=(), tail=()):
    out = [Cue(0, 0, 900, h) for h in head] + cues
    last = cues[-1].end_ms
    out += [Cue(0, last + 1000 * (k + 1), last + 1000 * (k + 1) + 800, t) for k, t in enumerate(tail)]
    return [Cue(i + 1, c.start_ms, c.end_ms, c.text) for i, c in enumerate(out)]


def test_retail_credit_with_full_name_is_professional():
    v = score_greek(with_edges(body(), tail=["Υποτιτλισμός:", "Γιώργος Λυκούδης"]))
    assert v.label == "professional"
    assert v.score >= 3
    assert any("Γιώργος Λυκούδης" in r for r in v.reasons)


def test_credit_name_on_the_same_line():
    v = score_greek(with_edges(body(), tail=["Απόδοση διαλόγων: Φίλιππος Ηρακλειώτης"]))
    assert v.label == "professional"


def test_netflix_card_is_professional():
    v = score_greek(with_edges(body(), head=["ΜΙΑ ΠΡΩΤΟΤΥΠΗ ΣΕΙΡΑ ΤΟΥ NETFLIX"]))
    assert v.label == "professional"


def test_fan_nicknames_are_amateur():
    for tail in (["Απόδοση-Επιμέλεια: sparta"], ["Απόδοση διαλόγων: marios2016"],
                 ["Απόδοση διαλόγων/ Μετάφραση.", "SAKIS974-(SAKIS DAM)"],
                 ["♥ Να είστε καλά ♥", "♥ ♫ m i s h a ♫ ♥"],
                 ["Sync: nasos_mik"], ["www.greeksubs.gr"],
                 ["Υποτιτλισμός: Γιώργος Λυκούδης", "Sync by repair"]):
        v = score_greek(with_edges(body(), tail=tail))
        assert v.label == "amateur", (tail, v)


def test_no_credit_frame_snapped_is_unknown_but_better_than_unsnapped():
    snapped = score_greek(body(frame=1000 / 23.976))
    plain = score_greek(body())
    assert snapped.label == plain.label == "unknown"
    assert snapped.score > plain.score


def test_credits_only_count_at_the_edges():
    cues = body(80)
    cues[40] = Cue(41, cues[40].start_ms, cues[40].end_ms, "Υποτιτλισμός: Γιώργος Λυκούδης")
    assert score_greek(cues).label == "unknown"


def test_all_caps_greek_credit_name_is_professional():
    v = score_greek(with_edges(body(), tail=["ΑΠΟΔΟΣΗ ΔΙΑΛΟΓΩΝ: ΤΣΟΥΤΣΟΥ ΕΛΙΝΑ"]))
    assert v.label == "professional"
    assert any("ΤΣΟΥΤΣΟΥ ΕΛΙΝΑ" in r for r in v.reasons)


def ocr(cues, every=1):
    # Latin o, M and v inside Greek words, as an OCR of a DVD subtitle leaves them.
    return [Cue(c.index, c.start_ms, c.end_ms, "Θα μπoρoύσε o Mελ Γκίμπσov.") if i % every == 0 else c
            for i, c in enumerate(cues)]


def test_ocr_latin_letters_inside_greek_words_are_amateur_even_with_a_credit():
    v = score_greek(with_edges(ocr(body()), tail=["Απόδοση διαλόγων: Φίλιππος Ηρακλειώτης"]))
    assert v.label == "amateur"
    assert any("mixed" in r for r in v.reasons)


def test_a_few_mixed_script_words_do_not_veto_a_credit():
    v = score_greek(with_edges(ocr(body(200), every=200), tail=["Απόδοση διαλόγων: Φίλιππος Ηρακλειώτης"]))
    assert v.label == "professional"


def test_a_fan_word_in_the_credit_name_vetoes_the_credit():
    v = score_greek(with_edges(body(), tail=["Μετάφραση: ΟΜΑΔΑ ΣΥΓΧΡΟΝΙΣΜΟΥ"]))
    assert v.label == "amateur"


def test_ocr_check_gives_the_same_verdict_for_decomposed_accents():
    import unicodedata

    def damaged(form):
        return [Cue(c.index, c.start_ms, c.end_ms, unicodedata.normalize(form, "Είσαι καλόs; Πολύ καλόs."))
                for c in body()]

    nfc = score_greek(with_edges(damaged("NFC"), tail=["Απόδοση διαλόγων: Φίλιππος Ηρακλειώτης"]))
    nfd = score_greek(with_edges(damaged("NFD"), tail=["Απόδοση διαλόγων: Φίλιππος Ηρακλειώτης"]))
    assert nfc.label == nfd.label == "amateur"


def test_a_decomposed_credit_line_still_counts():
    import unicodedata

    v = score_greek(with_edges(body(), tail=[unicodedata.normalize("NFD", "Απόδοση διαλόγων: Φίλιππος Ηρακλειώτης")]))
    assert v.label == "professional"
