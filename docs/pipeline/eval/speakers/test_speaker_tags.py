"""Tests for speaker_tags.py. Run: python3 -I docs/pipeline/eval/speakers/test_speaker_tags.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import speaker_tags as st  # noqa: E402


class TagTests(unittest.TestCase):
    def test_name_tags(self):
        self.assertEqual(st.extract_tag("<i>[Narrator]</i>\n<i>THIS IS MICHAEL.</i>"), "Narrator")
        self.assertEqual(st.extract_tag("[Tobias]\nI'M A NEVER-NUDE."), "Tobias")
        self.assertEqual(st.extract_tag("<i>[Man Narrating]</i>\n<i>THIS IS</i>"), "Narrator")
        self.assertEqual(st.extract_tag("<i>- [Gob] HI.</i>"), "Gob")
        self.assertEqual(st.extract_tag("- <i>[Gob] HI.</i>"), "Gob")

    def test_role_tags_are_kept_as_roles(self):
        self.assertEqual(st.extract_tag("[Man On Loudspeaker]\nATTENTION"), "Man On Loudspeaker")
        self.assertTrue(st.is_role("Man On Loudspeaker"))
        self.assertTrue(st.is_role("Guard"))
        self.assertFalse(st.is_role("Gob"))

    def test_sound_tags_are_not_names(self):
        for t in ["[Laughing]", "[Squeals]", "[Chuckles]", "[Sighs]", "<i>[Pounding Drums]</i>",
                  "[Mispronounces Gob]", "[Maeby Singing In Shower]", "<i>[Applause, Cheering]</i>",
                  "THAT WOULD MEAN... [Shuddering]", "[All Arguing]", "[Beeps]",
                  "[Shower Running]", "[Lindsay Clears Throat]"]:
            self.assertIsNone(st.extract_tag(t), t)

    def test_no_tag(self):
        self.assertIsNone(st.extract_tag("LOOK WHAT THEY'VE DONE, MICHAEL."))


class PartTests(unittest.TestCase):
    def test_dash_cue_splits_by_text_length(self):
        parts = st.split_parts(10.0, 14.0, "- [Gob] HI.\n- HELLO THERE, GOB.")
        self.assertEqual(len(parts), 2)
        (s1, e1, t1, tag1), (s2, e2, t2, tag2) = parts
        self.assertEqual((s1, tag1, tag2), (10.0, "Gob", None))
        self.assertAlmostEqual(e1, s2)
        self.assertLess(e1 - s1, e2 - s2)
        self.assertEqual(e2, 14.0)

    def test_tag_inside_cue_starts_a_part(self):
        parts = st.split_parts(0.0, 4.0, "AND I'M PUTTING BUSTER\nIN CHARGE.\n[Gob] THAT'S A GOOD CHOICE.")
        self.assertEqual([p[3] for p in parts], [None, "Gob"])

    def test_sound_tag_inside_cue_does_not_split(self):
        self.assertEqual(len(st.split_parts(0.0, 2.0, "HOW ARE YOU?\n[Laughing]")), 1)

    def test_plain_cue_is_one_part(self):
        self.assertEqual(st.split_parts(1.0, 2.0, "[George]\nNO TOUCHING."), [(1.0, 2.0, "[George]\nNO TOUCHING.", "George")])


class ClusterTests(unittest.TestCase):
    SEGS = [(0.0, 5.0, "A"), (5.0, 10.0, "B")]

    def test_dominant_cluster(self):
        self.assertEqual(st.dominant(self.SEGS, 3.0, 7.5), ("B", 2.5 / 4.5))
        self.assertEqual(st.dominant(self.SEGS, 20.0, 21.0), (None, 0.0))

    def test_name_clusters_majority(self):
        votes = [("A", "Narrator"), ("A", "Narrator"), ("A", "Gob"), ("B", "Gob")]
        self.assertEqual(st.name_clusters(votes), {"A": "Narrator", "B": "Gob"})

    def test_name_clusters_min_votes(self):
        votes = [("A", "Narrator"), ("A", "Narrator"), ("B", "Gob")]
        self.assertEqual(st.name_clusters(votes, min_votes=2), {"A": "Narrator"})

    def test_leave_one_out_respects_min_votes(self):
        # Two A votes: leaving one out leaves one, below min_votes=2.
        self.assertEqual(st.leave_one_out([("A", "Narrator"), ("A", "Narrator")], min_votes=2), [None, None])

    def test_leave_one_out(self):
        # The single B vote cannot name B when it is left out.
        votes = [("A", "Narrator"), ("A", "Narrator"), ("A", "Gob"), ("B", "Gob")]
        self.assertEqual(st.leave_one_out(votes), [True, True, False, None])


class OffsetTests(unittest.TestCase):
    def test_finds_offset_and_scale(self):
        k = 1000 / 1001
        cues = [(i, 10.0 * i, 10.0 * i + 3, "x") for i in range(1, 100)]
        segs = [(k * s - 1.5, k * e - 1.5, "A") for _, s, e, _ in cues]
        scale, off = st.best_offset(cues, segs, -3, 3, 0.05)
        self.assertAlmostEqual(scale, k)
        self.assertAlmostEqual(off, -1.5, places=2)


class OverlapTests(unittest.TestCase):
    def test_overlapping_segments_count_once(self):
        segs = [(0.0, 1.0, "A"), (0.0, 1.0, "B")]
        self.assertAlmostEqual(st.speech_overlap([(0.0, 1.0)], segs, 0.0), 1.0)


class GenderTests(unittest.TestCase):
    def test_gender_from_f0(self):
        self.assertEqual(st.gender_from_f0(110.0, 200)[0], "m")
        self.assertEqual(st.gender_from_f0(220.0, 200)[0], "f")
        self.assertEqual(st.gender_from_f0(165.0, 200)[0], "?")
        self.assertEqual(st.gender_from_f0(110.0, 5)[0], "?")  # too few voiced frames
        self.assertGreater(st.gender_from_f0(100.0, 200)[1], st.gender_from_f0(140.0, 200)[1])


if __name__ == "__main__":
    unittest.main()
