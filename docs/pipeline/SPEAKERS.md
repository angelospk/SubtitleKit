# Speaker names and voice gender per cue (feasibility, 2026-10-24)

Goal: for each subtitle cue, know in code who speaks and whether the voice is
male or female, so that the Greek translation can pick the right gender,
number and register per character. This is an experiment, not production.

Code: `docs/pipeline/eval/speakers/speaker_tags.py` (tests:
`python3 -I docs/pipeline/eval/speakers/test_speaker_tags.py`).

## Method

1. Diarization: speakrs (Rust port of pyannote community-1, CoreML on the
   MacBook) on the BluRay audio of Arrested Development S01E01 (REWARD, 1304 s,
   mono 16 kHz). 16 s for the episode. Output: `eval/speakers/ad_s01e01.diar.txt`,
   14 clusters.
2. English HI subtitle from OpenSubtitles (REST API): `Pilot.DVD.HI.cc.en.20FOX`
   (subtitle 9641874, 387 cues). The `EXT` release (9641875) is the extended
   DVD cut (28 min) and does not fit the broadcast audio.
3. Alignment: grid search for scale and offset that maximise the overlap of cue
   spans with diarized speech (overlapping speakers count once). Result:
   audio time = 1000/1001 x subtitle time - 0.9 s. The 0.1 % factor is the
   NTSC 24 / 23.976 ratio; a single offset is not enough, the drift is about
   1 s over 15 min.
4. Cue parts: a cue splits at dash lines and at lines that start with a name
   tag (`[Gob] THAT'S A GOOD CHOICE.`); time is shared by text length. Each
   part gets the cluster with the most overlap.
5. Tags: `[Name]` at the start of a part. Sound tags (`[Laughing]`,
   `[Lindsay Clears Throat]`, `[Maeby Singing In Shower]`) are not names. Role
   tags (`[Man]`, `[Guard]`, `[Man On Loudspeaker]`) do not vote.
6. Naming: each cluster takes the majority name of the tagged parts on it
   (`--min-votes`, default 1). Other clusters stay `unknown_N`.
7. Gender: median F0 (praat, 10 ms) over all speech of the cluster.
   `< 150 Hz` = m, `> 180 Hz` = f, between = `?`. The band was set before the
   check, from textbook ranges, and not tuned.
8. Output per cue part (a dash cue gives two records with the same `idx`):
   `{idx, start, end, cluster, speaker, gender, confidence, purity, tag}`
   (`eval/speakers/ad_s01e01.cues.jsonl`, text removed). `purity` is the
   share of the part's speech on its cluster; `confidence` = purity x gender
   confidence (0 when there is no F0 evidence).

Cue-level numbers below use the first part of each cue.

Ground truth, by hand from dialogue and plot (not by listening):
`gt_clusters.tsv` (who each cluster mostly is) and `gt_gender.tsv` (20 cues).

## Results (AD S01E01)

| Metric | Value |
|---|---|
| Name-tagged cue parts in the HI subtitle (387 cues) | 29 (23 Narrator, 2 Tobias, 1 each Michael, Gob, George, Maeby) |
| (a) Tagged part agrees with its cluster's name (in-sample) | 28/29 = 96.6 % |
| (a) Same, leave-one-out | 25/26 = 96.2 % (3 tags are the only vote of their cluster) |
| (a) Tagged part lands on the right person's cluster (vs `gt_clusters.tsv`) | **26/29 = 89.7 %** |
| Named clusters that are right | 3/5 (Narrator, Tobias, George right; Michael and Gob swapped) |
| (b) Cues that get a name, min-votes 1 | 63.6 % |
| (b) Cues on a rightly named cluster, min-votes 1 (proxy, see note) | **35.7 %** |
| (b) Cues that get a name, min-votes 2 (both clusters right) | 29.5 % (Narrator, Tobias only) |
| (c) Gender, 20 hand-checked cues | **12/20 right, 4 `?`, 4 wrong** |

Note on (b): "rightly named" is checked per cluster, not per cue. A cue of
another speaker that sits in a rightly named cluster (error 5 below) still
counts, so 35.7 % is an upper bound for right names.

Median F0 per cluster (Hz): Narrator 121, George 132, Michael 149, Gob 158,
Tobias 167, Buster 189, George Michael 214, Lucille 224, Maeby 242,
Lindsay 245.

What works:

- The clusters are clean per main character: 12 of 14 clusters are mostly
  one person (10 family members, a news anchor, a reporter), 2 are mixed. All 23 Narrator
  tags fall on one cluster.
- Alignment is automatic and accurate enough (scale + offset).
- Gender is right for the adult women (Lucille, Lindsay), Maeby, and the low
  male voices (Narrator, George, Michael).

What does not work:

- US closed captions tag a speaker only when the speaker is off screen. So
  the main on-screen characters (Lucille, Lindsay, Buster, George Michael,
  Maeby) never get a name from tags, and a cluster with one tag is fragile.
- F0 alone cannot separate a teenage boy (George Michael, 214 Hz) or a
  high-voiced man (Buster, 189 Hz) from women. Two male clusters (Gob, Tobias)
  fall in the 150-180 Hz band and stay `?`.

## Five errors and their effect on the Greek translation

1. **Michael and Gob swapped.** Cue 27 `[Michael] SO, THIS IS THE MAGIC
   TRICK, HUH?` is off screen; its loose CC timing (72.1-75.1 s) covers Gob's
   next line (diarized 73.4-78.8 s), while Michael speaks only 71.9-72.4 s. The
   single `[Gob]` tag (cue 257) lands on Michael's cluster. Result: 86 Michael
   cues say "Gob" and 22 Gob cues say "Michael". Gender comes from the
   cluster, not the name, so it does not swap: Michael's cues keep m (149 Hz),
   Gob's cues stay `?` (158 Hz). The register is wrong (Gob's bluster on the
   straight man), and in cue 28 `ILLUSION, MICHAEL` the model sees Michael
   address himself.
2. **George Michael as female** (cluster F0 214 Hz). Cue 342 `SINCE MOM DIED,
   IT'S BEEN KIND OF LONELY` becomes «ένιωθα μόνη» instead of «μόνος». This is
   the exact error the system should prevent, now made with confidence.
3. **Buster as female** (189 Hz). His lines in this episode have few
   gender-marked words, but any "I'm sure / ready / scared" would become
   «σίγουρη / έτοιμη / φοβισμένη».
4. **Maeby's song on the Narrator cluster.** Cue 380 `[Maeby] ♪ I'M NOT THAT
   INNOCENT ♪` overlaps the narrator's voice-over, so it gets Narrator, m:
   «Δεν είμαι τόσο αθώος» instead of «αθώα». Her only tag is lost too.
5. **On-screen lines inside the Narrator cluster.** Cue 5 `THIS IS MICHAEL'S
   MOTHER. / LOOK WHAT THEY'VE DONE, MICHAEL.` mixes the narrator and Lucille
   without a dash, so all of it is Narrator, m. Cue 56 (Michael to his son) and
   cue 221 (Gob) are labelled Narrator too. The translator may use the
   narrator's storyteller register for dialogue, and a female line can get
   male forms.

## Verdict

Feasible as a **consistency signal**, not yet as a truth signal. Clusters give
a stable per-character id across the episode (`unknown_N` is still useful: the
same voice gets the same forms everywhere). Names from HI tags reach about a
third of the cues, and F0 gender is right in 60 % with 20 % wrong. Do not
force gender from F0 in the prompt; pass it as a hint only when confidence is
high, and let text evidence win.

Next steps that look cheap (not done here):

- Name clusters with an LLM: give it the lines of each cluster and the cast
  list; the lines of cluster 12 make "George Michael" obvious.
- Gender from the name once a cluster is named (TMDB cast lists the actor's
  gender); F0 only for unnamed clusters.
- A gender classifier on speakrs voice embeddings instead of F0.
- Split mixed cues without a dash at the diarization turn boundary.

## Reproduce

On the MacBook (`~/spk-exp`, audio from `~/sync-exp/data/arrested/audio`):

```bash
uv venv .venv && uv pip install --python .venv/bin/python numpy praat-parselmouth
.venv/bin/python -I speaker_tags.py --wav stream.wav --diar diar.txt \
  --srt "Arrested Development S01E01 Pilot.DVD.HI.cc.en.20FOX.srt" \
  --clusters gt_clusters.tsv --gt gt_gender.tsv --out cues.jsonl [--min-votes 2]
```

`diar.txt` comes from a small Rust program on speakrs
(`OwnedDiarizationPipeline::from_pretrained(ExecutionMode::CoreMl)`, then
`discrete_diarization.to_segments()`), one `start end SPEAKER_xx` per line.
