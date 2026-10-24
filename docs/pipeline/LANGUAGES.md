# Source languages for Greek subtitles: what each one gives (2026-10-24)

Question (Harold): Polish worked as the base for The Housemaid (E37/E38), but another film may have no Polish track.
Which languages can be the base, which can give signals, and which strategy fits the tracks a release has?

Scripts: `eval/langs/compact.py` (length, code only) and `eval/langs/signals.py` (grammar signals, Sonnet).
Data outside git: `~/pipeline-demo/eval/langs/`.

## Method

Two films, two Greek references written by people:

- **Euphoria S03E01**: the professional Greek track and 33 other tracks of the same WEB-ETHEL release (same timing).
  Teenagers: almost no εσείς (2 cues).
- **The Housemaid (2025)**: Harold's own Greek subtitle (OpenSubtitles 13551469, «Υποτιτλισμός: haroldpoi») as the
  reference; Polish and Spanish WEB-ETHEL; 17 languages from the OpenSubtitles REST API (`/download`, 18 of the daily
  quota; the `dl.` link gave 401 and was not retried). Other releases: every track is synced to the Greek first
  (`sync_track`); Bulgarian did not sync confidently and is left out of the signals.

Signals: Sonnet reads only the grammar of a line (2 neighbour lines of the same language for context) and reports
speaker gender (`sg`), addressee gender (`ag`), number of "you" (`num`), formality (`v`: T / V) and gender of "we"
(`wg`). First on the Greek reference, then on each language for the lines that play during the Greek cues with a
decision. **Coverage** = share of Greek decisions where the language shows a value; **agreement** = share of those
values that match the Greek. Small samples: speaker / addressee gender has 13 / 27 decisions in Euphoria and 31 / 30
in The Housemaid; εσείς to one person has 2 and 12; gendered "we" 0 and 4. Read those columns as a direction, not a
ranking.

## Findings

All numbers come from two films and from the tracks they happen to have. Read them as a first map, not as rules.

1. **Length of the source track** (characters relative to the English track of the same film; this measures the
   source, not the Greek that a translation from it would give, and a short track may also have dropped content).
   Short in both films: Polish (69 % / 79 %), Slovenian (78 % / 76 %), Croatian (81 % / 80 %), Czech (75 % / 82 %).
   Lithuanian is short in Euphoria (75 %, not in The Housemaid); Bulgarian is short in Euphoria (74 %) but not in
   The Housemaid (91 %, a fan track with 40 % of cues over 17 CPS). Spanish and French are short in one
   film and long in the other (Euphoria French 84 %, Spanish 90-94 %; Housemaid Spanish 86 %, French 95 %), so length
   depends on the subtitler as much as on the language. Italian, German and Portuguese are 94-116 % in both. The
   human Greek tracks are 87 % (Euphoria) and 93 % (Harold).
2. **Number of "you" (one / several)** is shown by almost every language with 94-100 % agreement; coverage is lower
   in Scandinavian, Dutch and the Asian tracks (39-65 %).
3. **Addressee gender** («είσαι έτοιμη»; 27 and 30 Greek decisions): Hebrew is best in Euphoria (89 % coverage, 96 %
   agreement); then Croatian, Latvian, Serbian, Portuguese, Spanish, Romanian (56-78 %). Vietnamese 52 % (pronoun
   choice), Icelandic 48 %; German, Dutch, Scandinavian, Finnish, Estonian, Hungarian and Turkish 4-30 %.
4. **Speaker gender** («ήμουν σίγουρη»; 13 and 31 decisions): Slavic (Slovenian, Croatian, Czech, Slovak, Ukrainian
   61-77 %), Romance (Portuguese, Romanian, French, Italian 46-70 %), Hebrew and Macedonian 69 %, Icelandic 62 %.
   German, Dutch, Hungarian 0-13 %; Finnish, Estonian, Turkish, Scandinavian 0-8 %.
5. **εσείς to one person** (The Housemaid only; 12 Greek cues, fewer for a language when its shared blocks are left
   out). Two kinds of language:
   - precise but missing many: Romanian (finds 5 of 12; its own V cues are V / T in Harold's Greek: 5 / 1), Turkish
     (6 of 12; 6 / 2), Spanish (3 of 10; 3 / 1), Dutch (2 of 8; 2 / 1), Polish (1 of 10; 1 / 1);
   - finding more but over-marking: Czech (9 of 12; 9 / 9), Serbian (6 of 8; 6 / 7), and far more Ukrainian (6 / 31),
     German (5 / 39), Russian (8 / 75).
   The V / T counts are among the Greek decision cues only (where the languages were labelled), so they are a
   conditional precision, not one over the whole track. Polish subtitles use «pani / pan» rarely (6 cues in the film).
6. **A track can be wrong.** The Italian Housemaid track speaks of Millie in the masculine («fortunato»,
   «imbranato»): gender agreement 35-38 %, which suggests a machine or English-based translation. (The Slovak track
   has the same 2161 cues, so the same source timing, but its gender agrees 89-100 %.) A disagreement on gender with
   another language only flags a track for a look; it does not prove which track is wrong.
7. **Harold's own εσείς is wider than the E38 sheet.** In his subtitle Millie says εσείς to Nina at the job interview
   (3, 52, 109) and at the last interview (1794), strangers at the school say εσείς (379, 381), and the detective says
   εσείς to Nina (1707-1721). E38 has εσύ in all of them: the sheet makes "employer at home" εσύ for the whole film and
   does not know the detective (an unnamed voice). Polish «pani» (1572, 1583) and Spanish «Usted» (1572) also said
   εσείς there; the E38 rule check turned Gemini's εσείς into εσύ.

Limits of the method: a time-aligned block of a language can hold two turns (a question and its answer) that the
Greek splits in two cues; such shared blocks are left out of the tables (2-172 cues per language, most for Slovenian
and Serbian, whose cues are long). The labels are one Sonnet pass per language, without a second judge.

## Language profiles (measured where the films allow)

| group | languages | source length | speaker gender | addressee gender | one / several | εσείς |
|---|---|---|---|---|---|---|
| West / South Slavic | pl, cs, sk, sl, hr, sr, mk, bg | mostly short | yes | yes | yes | pl very few; cs / sr find more, over-mark |
| East Slavic | ru, uk | medium | yes | some | yes | over-marked |
| Baltic | lt, lv | short (Euphoria) | some | yes (lv) | yes | not measured (no εσείς in Euphoria) |
| Romance | es, pt, fr, ro, it | short to long, by subtitler | yes | yes | yes | es / ro precise, few |
| Hebrew | he | other script | yes | best | yes | (no V form) |
| Germanic | de, nl, da, sv, nb, is | medium to long | little (is: some) | little | yes, weaker in Nordic | de over-marked |
| Finnic, Hungarian, Turkish | fi, et, hu, tr | medium | no | little | yes | tr precise, few |
| Asian | id, ms, vi, th, mn | other script / n.a. | no | vi some | weak | weak |

## Strategy by the tracks a release has (provisional)

Only "Polish base + Spanish signals + English meaning guard" is tested (E38). Every other row is a hypothesis from
the signal tables and needs one translation run before it is trusted. The base is the track Gemini translates from;
companions only give signals through the address map and the rule check; English is the meaning guard. A base should
be an official (streaming / Blu-ray) track; measure its length on the film itself, since it depends on the subtitler.

| tracks available (besides English) | base | companions for signals | status |
|---|---|---|---|
| Polish + Spanish | Polish | Spanish | tested (E38) |
| Polish + another Romance track | Polish | Portuguese / French / Romanian | hypothesis |
| no Polish; a short Slavic track (cs, sk, sl, hr, sr, lt, bg) | the shortest of them on this film | one Romance track + Czech or Serbian for εσείς candidates | hypothesis |
| only Russian / Ukrainian among Slavic | the shorter of them | one Romance track | hypothesis; their εσείς marks are too many to use alone |
| only Romance tracks | the shortest Romance track if it is clearly shorter than English (e.g. Euphoria French 84 %), else English (E36a route) | the other Romance tracks | hypothesis |
| only Germanic / Nordic / Finnic / Asian | English | one / several from all of them; gender only where measured (Icelandic speaker and addressee gender, Vietnamese addressee gender) | hypothesis |
| Hebrew among the tracks | (any) | add Hebrew for addressee gender | hypothesis |

εσείς from several languages (hypothesis): take a cue as εσείς when a precise language (ro, tr, es, nl, pl) marks it,
or when an over-marking one (cs, sr) marks it and the scene is a first meeting, an interview or an official role;
never from Russian, Ukrainian or German alone.

## Appendix A: length per track (compact.py)

### Euphoria S03E01

| track | cues | characters | vs English | CPS > 17 | CPS > 20 |
|---|---|---|---|---|---|
| pol (28) | 580 | 14800 | 69 % | 11.0 % | 4.3 % |
| bul (5) | 543 | 15753 | 74 % | 5.0 % | 1.1 % |
| cze (6) | 591 | 16083 | 75 % | 4.9 % | 1.0 % |
| lit (21) | 607 | 16121 | 75 % | 4.8 % | 0.0 % |
| slv (33) | 516 | 16778 | 78 % | 3.7 % | 0.4 % |
| slo (32) | 613 | 16926 | 79 % | 11.9 % | 2.1 % |
| nob (26) | 571 | 17109 | 80 % | 2.3 % | 0.0 % |
| srp (34) | 519 | 17192 | 80 % | 2.3 % | 0.2 % |
| hrv (16) | 521 | 17440 | 81 % | 1.9 % | 0.0 % |
| rum (31) | 578 | 17701 | 83 % | 14.7 % | 2.1 % |
| mac (23) | 520 | 17843 | 83 % | 3.8 % | 0.8 % |
| fre (14) | 669 | 18013 | 84 % | 15.2 % | 0.1 % |
| est (12) | 613 | 18049 | 84 % | 7.0 % | 0.0 % |
| lav (22) | 600 | 18361 | 86 % | 6.7 % | 0.0 % |
| ice (19) | 567 | 18372 | 86 % | 3.2 % | 0.0 % |
| swe (35) | 568 | 18386 | 86 % | 2.6 % | 0.0 % |
| dut (27) | 580 | 18413 | 86 % | 2.4 % | 0.0 % |
| fin (13) | 593 | 18536 | 87 % | 7.3 % | 0.0 % |
| Greek (professional) | 601 | 18672 | 87 % | 5.2 % | 0.0 % |
| vie (38) | 626 | 18706 | 87 % | 16.3 % | 5.8 % |
| hun (17) | 589 | 18914 | 88 % | 16.3 % | 0.0 % |
| tur (37) | 652 | 18982 | 89 % | 17.6 % | 4.9 % |
| spa (10) | 688 | 19263 | 90 % | 25.3 % | 5.8 % |
| dan (7) | 562 | 19526 | 91 % | 10.1 % | 0.0 % |
| ita (20) | 646 | 20065 | 94 % | 22.9 % | 8.2 % |
| spa (11) | 652 | 20115 | 94 % | 20.9 % | 9.0 % |
| por (29) | 628 | 20383 | 95 % | 19.7 % | 1.6 % |
| mon (24) | 690 | 20429 | 95 % | 27.8 % | 13.0 % |
| ind (18) | 655 | 20463 | 96 % | 22.1 % | 10.7 % |
| ger (8) | 594 | 20468 | 96 % | 25.3 % | 0.0 % |
| may (25) | 700 | 20585 | 96 % | 32.6 % | 16.9 % |
| English | 706 | 21404 | 100 % | 34.7 % | 19.5 % |
| por (30) | 760 | 21598 | 101 % | 49.3 % | 30.8 % |
| heb (15) | 607 | 15885 | (other script) | 2.1 % | 0.0 % |
| tha (36) | 721 | 17113 | (other script) | 8.9 % | 2.8 % |

### The Housemaid

| track | cues | characters | vs English | CPS > 17 | CPS > 20 |
|---|---|---|---|---|---|
| sl | 1182 | 40401 | 76 % | 3.0 % | 0.0 % |
| pl | 1654 | 41898 | 79 % | 7.2 % | 0.5 % |
| hr | 1752 | 42762 | 80 % | 15.7 % | 4.7 % |
| cs | 1674 | 43614 | 82 % | 8.7 % | 2.3 % |
| uk | 1604 | 45348 | 85 % | 12.5 % | 3.5 % |
| es | 1749 | 45906 | 86 % | 25.0 % | 8.5 % |
| nl | 1250 | 46376 | 87 % | 11.6 % | 3.8 % |
| tr | 1522 | 46592 | 88 % | 13.7 % | 5.0 % |
| sr | 1336 | 48064 | 90 % | 11.5 % | 3.8 % |
| ru | 1983 | 48188 | 91 % | 17.7 % | 7.8 % |
| bg | 1493 | 48422 | 91 % | 39.6 % | 23.4 % |
| Greek (Harold) | 1798 | 49499 | 93 % | 16.1 % | 3.9 % |
| fr | 1753 | 50339 | 95 % | 37.0 % | 15.7 % |
| pt-BR | 1865 | 50412 | 95 % | 26.2 % | 9.7 % |
| hu | 1914 | 51498 | 97 % | 27.9 % | 14.6 % |
| ro | 1907 | 52342 | 98 % | 25.8 % | 13.0 % |
| pt-PT | 1735 | 53143 | 100 % | 39.5 % | 18.2 % |
| English | 1985 | 53162 | 100 % | 25.4 % | 10.9 % |
| de | 1692 | 56166 | 106 % | 41.1 % | 5.3 % |
| sk | 2161 | 56979 | 107 % | 24.7 % | 12.5 % |
| it | 2161 | 61876 | 116 % | 33.6 % | 20.9 % |

## Appendix B: signals, Euphoria S03E01 (signals.py stats)

| language | sg cover / agree | ag cover / agree | num cover / agree | v cover / agree | wg cover / agree |
|---|---|---|---|---|---|
| Hebrew | 69 % / 89 % | 89 % / 96 % | 81 % / 96 % | 80 % / 100 % | 0 % / 0 % |
| Portuguese (track 29) | 54 % / 100 % | 63 % / 94 % | 85 % / 97 % | 78 % / 100 % | 0 % / 0 % |
| Latvian | 38 % / 100 % | 78 % / 100 % | 83 % / 98 % | 78 % / 99 % | 0 % / 0 % |
| Romanian | 42 % / 100 % | 58 % / 93 % | 84 % / 97 % | 80 % / 100 % | 0 % / 0 % |
| Spanish (track 10) | 54 % / 100 % | 63 % / 94 % | 81 % / 97 % | 78 % / 100 % | 0 % / 0 % |
| Spanish (track 11) | 31 % / 100 % | 56 % / 100 % | 77 % / 96 % | 76 % / 98 % | 0 % / 0 % |
| Italian | 58 % / 100 % | 56 % / 100 % | 78 % / 97 % | 76 % / 100 % | 0 % / 0 % |
| Czech | 83 % / 100 % | 59 % / 81 % | 79 % / 97 % | 76 % / 92 % | 0 % / 0 % |
| Icelandic | 67 % / 88 % | 48 % / 85 % | 78 % / 97 % | 76 % / 99 % | 0 % / 0 % |
| Macedonian | 67 % / 100 % | 61 % / 100 % | 86 % / 97 % | 83 % / 99 % | 0 % / 0 % |
| Slovak | 50 % / 100 % | 52 % / 100 % | 76 % / 97 % | 75 % / 98 % | 0 % / 0 % |
| Croatian | 75 % / 100 % | 70 % / 100 % | 86 % / 96 % | 80 % / 100 % | 0 % / 0 % |
| Serbian | 58 % / 100 % | 78 % / 100 % | 85 % / 96 % | 81 % / 99 % | 0 % / 0 % |
| Lithuanian | 46 % / 100 % | 56 % / 93 % | 73 % / 98 % | 69 % / 100 % | 0 % / 0 % |
| Estonian | 0 % / 0 % | 19 % / 100 % | 75 % / 99 % | 74 % / 100 % | 0 % / 0 % |
| French | 46 % / 100 % | 50 % / 100 % | 73 % / 98 % | 71 % / 95 % | 0 % / 0 % |
| Turkish | 0 % / 0 % | 27 % / 100 % | 76 % / 98 % | 74 % / 99 % | 0 % / 0 % |
| Finnish | 0 % / 0 % | 7 % / 100 % | 73 % / 99 % | 70 % / 100 % | 0 % / 0 % |
| Portuguese (track 30) | 31 % / 100 % | 59 % / 100 % | 77 % / 96 % | 56 % / 100 % | 0 % / 0 % |
| Slovenian | 75 % / 100 % | 57 % / 100 % | 79 % / 96 % | 73 % / 99 % | 0 % / 0 % |
| Bulgarian | 36 % / 100 % | 48 % / 100 % | 72 % / 97 % | 72 % / 100 % | 0 % / 0 % |
| Hungarian | 0 % / 0 % | 15 % / 100 % | 74 % / 94 % | 73 % / 97 % | 0 % / 0 % |
| Polish | 25 % / 100 % | 58 % / 93 % | 69 % / 98 % | 70 % / 99 % | 0 % / 0 % |
| German | 0 % / 0 % | 24 % / 83 % | 71 % / 98 % | 73 % / 94 % | 0 % / 0 % |
| Danish | 0 % / 0 % | 24 % / 100 % | 63 % / 98 % | 69 % / 100 % | 0 % / 0 % |
| Dutch | 0 % / 0 % | 30 % / 100 % | 54 % / 97 % | 67 % / 99 % | 0 % / 0 % |
| Swedish | 0 % / 0 % | 11 % / 100 % | 63 % / 97 % | 65 % / 99 % | 0 % / 0 % |
| Indonesian | 0 % / 0 % | 22 % / 100 % | 57 % / 96 % | 57 % / 99 % | 0 % / 0 % |
| Norwegian | 8 % / 100 % | 12 % / 100 % | 58 % / 99 % | 58 % / 100 % | 0 % / 0 % |
| Malay | 0 % / 0 % | 4 % / 100 % | 58 % / 96 % | 56 % / 100 % | 0 % / 0 % |
| Mongolian | 0 % / 0 % | 11 % / 100 % | 53 % / 96 % | 53 % / 98 % | 0 % / 0 % |
| Vietnamese | 0 % / 0 % | 52 % / 100 % | 48 % / 99 % | 32 % / 85 % | 0 % / 0 % |
| Thai | 0 % / 0 % | 11 % / 100 % | 39 % / 99 % | 36 % / 88 % | 0 % / 0 % |
Greek decisions per signal (before each language's shared blocks are left out): {'sg': 13, 'ag': 27, 'num': 195, 'v': 185, 'wg': 0}

Greek V cues: 2

| language | Greek V found | language V (on Greek decision cues) | Greek V / T / unknown there |
|---|---|---|---|
| Bulgarian | 1 / 2 | 2 | 1 / 0 / 1 |
| Czech | 2 / 2 | 14 | 2 / 11 / 1 |
| Danish | 0 / 2 | 0 | 0 / 0 / 0 |
| German | 0 / 2 | 8 | 0 / 8 / 0 |
| Spanish (track 10) | 1 / 2 | 3 | 1 / 0 / 2 |
| Spanish (track 11) | 1 / 2 | 7 | 1 / 3 / 3 |
| Estonian | 2 / 2 | 2 | 2 / 0 / 0 |
| Finnish | 1 / 2 | 2 | 1 / 0 / 1 |
| French | 1 / 2 | 9 | 1 / 6 / 2 |
| Hebrew | 2 / 2 | 3 | 2 / 0 / 1 |
| Croatian | 1 / 2 | 3 | 1 / 0 / 2 |
| Hungarian | 0 / 2 | 7 | 0 / 4 / 3 |
| Indonesian | 2 / 2 | 6 | 2 / 1 / 3 |
| Icelandic | 0 / 2 | 0 | 0 / 0 / 0 |
| Italian | 2 / 2 | 4 | 2 / 0 / 2 |
| Lithuanian | 1 / 2 | 2 | 1 / 0 / 1 |
| Latvian | 0 / 2 | 1 | 0 / 1 / 0 |
| Macedonian | 0 / 2 | 3 | 0 / 0 / 3 |
| Mongolian | 2 / 2 | 8 | 2 / 2 / 4 |
| Malay | 2 / 2 | 5 | 2 / 0 / 3 |
| Norwegian | 0 / 2 | 0 | 0 / 0 / 0 |
| Dutch | 0 / 2 | 1 | 0 / 0 / 1 |
| Polish | 2 / 2 | 5 | 2 / 1 / 2 |
| Portuguese (track 29) | 1 / 2 | 3 | 1 / 0 / 2 |
| Portuguese (track 30) | 1 / 2 | 4 | 1 / 0 / 3 |
| Romanian | 2 / 2 | 3 | 2 / 0 / 1 |
| Slovak | 2 / 2 | 7 | 2 / 3 / 2 |
| Slovenian | 0 / 2 | 0 | 0 / 0 / 0 |
| Serbian | 2 / 2 | 5 | 2 / 1 / 2 |
| Swedish | 0 / 2 | 0 | 0 / 0 / 0 |
| Thai | 1 / 2 | 12 | 1 / 8 / 3 |
| Turkish | 1 / 2 | 4 | 1 / 1 / 2 |
| Vietnamese | 1 / 2 | 12 | 1 / 9 / 2 |

## Appendix C: signals, The Housemaid (signals.py --film housemaid stats)

| language | sg cover / agree | ag cover / agree | num cover / agree | v cover / agree | wg cover / agree |
|---|---|---|---|---|---|
| Romanian | 68 % / 100 % | 57 % / 94 % | 86 % / 99 % | 87 % / 99 % | 50 % / 100 % |
| Slovak | 71 % / 100 % | 60 % / 89 % | 86 % / 99 % | 87 % / 94 % | 50 % / 100 % |
| Hungarian | 10 % / 100 % | 7 % / 100 % | 86 % / 99 % | 88 % / 98 % | 0 % / 0 % |
| Portuguese (Brazil) | 61 % / 100 % | 63 % / 95 % | 86 % / 100 % | 79 % / 99 % | 0 % / 0 % |
| Italian | 65 % / 35 % | 53 % / 38 % | 84 % / 99 % | 86 % / 98 % | 0 % / 0 % |
| Czech | 63 % / 95 % | 50 % / 93 % | 84 % / 100 % | 86 % / 98 % | 75 % / 100 % |
| Portuguese (Portugal) | 70 % / 100 % | 60 % / 94 % | 85 % / 99 % | 86 % / 98 % | 0 % / 0 % |
| Croatian | 58 % / 100 % | 67 % / 100 % | 81 % / 99 % | 82 % / 98 % | 50 % / 50 % |
| Spanish (Latin America) | 48 % / 100 % | 57 % / 100 % | 82 % / 99 % | 81 % / 99 % | 0 % / 0 % |
| French | 61 % / 100 % | 50 % / 100 % | 79 % / 99 % | 79 % / 98 % | 0 % / 0 % |
| Serbian | 63 % / 100 % | 39 % / 89 % | 90 % / 100 % | 91 % / 98 % | 75 % / 100 % |
| Russian | 55 % / 100 % | 47 % / 100 % | 79 % / 99 % | 80 % / 83 % | 0 % / 0 % |
| Polish | 53 % / 100 % | 39 % / 91 % | 76 % / 99 % | 77 % / 99 % | 75 % / 100 % |
| German | 13 % / 100 % | 18 % / 80 % | 80 % / 99 % | 82 % / 91 % | 0 % / 0 % |
| Turkish | 0 % / 0 % | 25 % / 100 % | 80 % / 100 % | 81 % / 99 % | 0 % / 0 % |
| Ukrainian | 68 % / 100 % | 39 % / 91 % | 78 % / 99 % | 79 % / 92 % | 0 % / 0 % |
| Dutch | 11 % / 100 % | 4 % / 100 % | 76 % / 99 % | 78 % / 99 % | 0 % / 0 % |
| Slovenian | 73 % / 100 % | 41 % / 89 % | 81 % / 98 % | 81 % / 99 % | 75 % / 33 % |
Greek decisions per signal (before each language's shared blocks are left out): {'sg': 31, 'ag': 30, 'num': 595, 'v': 573, 'wg': 4}

Greek V cues: 12

| language | Greek V found | language V (on Greek decision cues) | Greek V / T / unknown there |
|---|---|---|---|
| French | 6 / 12 | 14 | 6 / 8 / 0 |
| German | 5 / 9 | 44 | 5 / 39 / 0 |
| Italian | 0 / 12 | 1 | 0 / 1 / 0 |
| Portuguese (Brazil) | 1 / 12 | 2 | 1 / 0 / 1 |
| Portuguese (Portugal) | 2 / 12 | 8 | 2 / 6 / 0 |
| Russian | 8 / 12 | 85 | 8 / 75 / 2 |
| Ukrainian | 6 / 10 | 38 | 6 / 31 / 1 |
| Czech | 9 / 12 | 19 | 9 / 9 / 1 |
| Slovak | 7 / 12 | 37 | 7 / 28 / 2 |
| Croatian | 5 / 12 | 14 | 5 / 8 / 1 |
| Serbian | 6 / 8 | 14 | 6 / 7 / 1 |
| Slovenian | 0 / 8 | 3 | 0 / 2 / 1 |
| Hungarian | 3 / 12 | 6 | 3 / 2 / 1 |
| Dutch | 2 / 8 | 3 | 2 / 1 / 0 |
| Romanian | 5 / 12 | 6 | 5 / 1 / 0 |
| Turkish | 6 / 12 | 8 | 6 / 2 / 0 |
| Polish | 1 / 10 | 2 | 1 / 1 / 0 |
| Spanish (Latin America) | 3 / 10 | 5 | 3 / 1 / 1 |
