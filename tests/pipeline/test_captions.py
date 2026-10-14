import json

from subtitlekit.pipeline.captions import (
    Caption,
    find_captions,
    greek_caps,
    insert_captions,
    is_caption_text,
    translate_captions,
)
from subtitlekit.pipeline.llm import LLMError, MockBackend
from subtitlekit.pipeline.srt import Cue


def test_is_caption_text():
    assert is_caption_text("ΚΑΠΟΥ ΣΤΟ ΤΣΙΟΥΑΟΥΑ")
    assert is_caption_text("CAPÍTULO OCHO / EL MUNDO".replace(" / ", "\n"))
    assert is_caption_text("50 000 WATTS")
    assert not is_caption_text("[DOOR SLAMS]") and not is_caption_text("♪ LA LA LA ♪")
    assert not is_caption_text("OK") and not is_caption_text("Hello there") and not is_caption_text("")


def test_greek_caps_drops_accents_and_keeps_split_diphthongs():
    assert greek_caps("Κάπου στο Τσιουάουα") == "ΚΑΠΟΥ ΣΤΟ ΤΣΙΟΥΑΟΥΑ"
    assert greek_caps("Το Χελφάιαρ ζει!") == "ΤΟ ΧΕΛΦΑΪΑΡ ΖΕΙ!"
    assert greek_caps("Μάικ") == "ΜΑΪΚ"
    assert greek_caps("Λύκειο Χόκινς") == "ΛΥΚΕΙΟ ΧΟΚΙΝΣ"


def tracks():
    # fr/es/de agree on a sign at 10 s; only fr has one at 30 s; all three caps-shout at 50 s,
    # where English has the chant too.
    fr = [Cue(1, 10000, 12000, "QUELQUE PART AU MEXIQUE"), Cue(2, 30000, 31000, "HÔTEL"),
          Cue(3, 50000, 52000, "USA ! USA !")]
    es = [Cue(1, 10200, 12100, "EN ALGÚN LUGAR DE MÉXICO"), Cue(2, 50000, 52000, "¡USA! ¡USA!")]
    de = [Cue(1, 9900, 11800, "IRGENDWO IN MEXIKO"), Cue(2, 50100, 52000, "USA! USA!")]
    es2 = [Cue(1, 10200, 12100, "EN ALGÚN LUGAR DE MÉXICO")]  # a second Spanish track: same language
    return [("fre", fr), ("spa", es), ("ger", de), ("spa", es2)]


def test_find_captions_needs_agreement_across_languages_and_skips_english_shouts():
    english = [Cue(1, 0, 2000, "Hello."), Cue(2, 50000, 52000, "USA! USA!")]
    caps = find_captions(tracks(), english, window_ms=1500, min_languages=3)
    assert len(caps) == 1
    c = caps[0]
    assert 9900 <= c.start_ms <= 10200 and 11800 <= c.end_ms <= 12100
    assert c.texts["fre"] == "QUELQUE PART AU MEXIQUE" and set(c.texts) == {"fre", "spa", "ger"}
    assert find_captions(tracks(), english, min_languages=2)[0].texts == c.texts  # 30 s: one language only


def test_translate_captions_one_call_greek_caps_and_null_means_not_a_caption():
    caps = [Caption(10000, 12000, {"fre": "QUELQUE PART AU MEXIQUE"}), Caption(20000, 21000, {"fre": "AH !"}),
            Caption(30000, 31000, {"fre": "RADIO WSQK"}), Caption(40000, 41000, {"fre": "HÔTEL"})]
    reply = {"1": "Κάπου στο Μεξικό, στη ώρα", "2": None, "3": "WSQK", "4": "Hotel"}
    backend = MockBackend(replies=[json.dumps(reply, ensure_ascii=False)])
    texts, problems = translate_captions(caps, backend)
    assert len(backend.prompts) == 1 and backend.prompts[0].startswith("You translate on-screen text")
    assert "QUELQUE PART AU MEXIQUE" in backend.prompts[0]
    assert texts == ["ΚΑΠΟΥ ΣΤΟ ΜΕΞΙΚΟ, ΣΤΗΝ ΩΡΑ", None, "WSQK", None]  # final-ν rule applies to caps  # "Hotel": Latin, not in any source text
    assert problems


def test_translate_captions_backend_failure_adds_nothing():
    def boom(prompt):
        raise LLMError("down")

    texts, problems = translate_captions([Caption(0, 1000, {"fre": "HÔTEL"})], MockBackend(replies=boom))
    assert texts == [None] and problems


def test_insert_captions_uses_free_time_renumbers_and_maps_old_indices():
    ours = [Cue(1, 0, 9000, "Πρώτη."), Cue(2, 9500, 10500, "Δεύτερη."), Cue(3, 14000, 15000, "Τρίτη."),
            Cue(4, 20000, 25000, "ΗΠΑ! ΗΠΑ!")]
    caps = [
        (Caption(10000, 12500, {}), "ΚΑΠΟΥ ΣΤΟ ΜΕΞΙΚΟ"),  # overlaps cue 2: placed after it, with the gap
        (Caption(14200, 14800, {}), "ΞΕΝΟΔΟΧΕΙΟ"),  # inside cue 3: no room
        (Caption(21000, 23000, {}), "ΗΠΑ!"),  # our caps cue is already there
        (Caption(30000, 32000, {}), "ΤΕΛΟΣ"),
    ]
    res = insert_captions(ours, caps, min_ms=700, gap_ms=84)
    texts = [c.text for c in res.cues]
    assert texts == ["Πρώτη.", "Δεύτερη.", "ΚΑΠΟΥ ΣΤΟ ΜΕΞΙΚΟ", "Τρίτη.", "ΗΠΑ! ΗΠΑ!", "ΤΕΛΟΣ"]
    assert [c.index for c in res.cues] == [1, 2, 3, 4, 5, 6]
    added = res.cues[2]
    assert added.start_ms == 10500 + 84 and added.end_ms == 12500
    assert res.mapping == {1: 1, 2: 2, 3: 4, 4: 5} and res.added == [3, 6]
    assert [r for _, r in res.skipped] == ["no room", "already there"]


def test_translate_captions_wants_greek_names_and_two_lines():
    caps = [Caption(0, 1000, {"spa": "SECUNDARIA HAWKINS"}), Caption(2000, 3000, {"spa": "RADIO WSQK"}),
            Caption(4000, 5000, {"spa": "APARTAMENTOS"})]
    reply = {"1": "Λύκειο Hawkins", "2": "Ράδιο WSQK",
             "3": "Επιπλωμένα διαμερίσματα\nμε ένα και δύο υπνοδωμάτια\nσε πολύ καλές τιμές για όλους τους φοιτητές της πόλης"}
    backend = MockBackend(replies=[json.dumps(reply, ensure_ascii=False)])
    texts, problems = translate_captions(caps, backend, names=[("Hawkins", "Χόκινς")])
    prompt = backend.prompts[0]
    assert '"Hawkins": "Χόκινς"' in prompt and "Greek letters" in prompt
    assert texts == [None, "ΡΑΔΙΟ WSQK", None]  # Latin name; three lines that do not fit two
    assert len(problems) == 2


def test_find_captions_keeps_adjacent_title_cards_apart():
    def cards(a, b):
        return [Cue(1, 10000, 11000, a), Cue(2, 11200, 12500, b)]

    tr = [("fre", cards("CHAPITRE HUIT", "LE MONDE À L'ENDROIT")), ("spa", cards("CAPÍTULO OCHO", "EL MUNDO DEL DERECHO")),
          ("ger", cards("KAPITEL ACHT", "DIE RICHTIGE WELT"))]
    caps = find_captions(tr, [], window_ms=1500, min_languages=3)
    assert [(c.start_ms, c.texts["fre"]) for c in caps] == [(10000, "CHAPITRE HUIT"), (11200, "LE MONDE À L'ENDROIT")]


def test_find_captions_counts_one_vote_per_language():
    tr = [("fre", [Cue(1, 10000, 11000, "HÔTEL")]), ("fre", [Cue(1, 10100, 11000, "HÔTEL")]),
          ("spa", [Cue(1, 10000, 11000, "HOTEL")])]
    assert find_captions(tr, [], min_languages=3) == []


def test_translate_captions_latin_only_as_a_token_every_language_keeps():
    src = {"fre": "RADIO WSQK", "spa": "RADIO WSQK", "ger": "SENDER WSQK"}
    caps = [Caption(i * 1000, i * 1000 + 500, src) for i in range(4)]
    reply = {"1": "WSQK", "2": "ΡΑΔΙΟ SQ", "3": "RADIO", "4": "ΡΑΔΙΟ ЖК"}
    texts, problems = translate_captions(caps, MockBackend(replies=[json.dumps(reply, ensure_ascii=False)]))
    assert texts == ["WSQK", None, None, None] and len(problems) == 3


def test_find_captions_second_tracks_of_a_language_do_not_make_a_duplicate():
    sign = {"fre": "HÔTEL", "spa": "HOTEL", "ger": "HOTEL"}
    tr = [(lang, [Cue(1, 10000 + k * 100, 12000, text)]) for k in range(2) for lang, text in sign.items()]
    caps = find_captions(tr, [], min_languages=3)
    assert len(caps) == 1 and set(caps[0].texts) == {"fre", "spa", "ger"}
