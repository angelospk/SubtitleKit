# Housemaid g2p residuals (first phrasebank test set)

Source: the 4 Sonnet audits (gpt-6.1-sol confirms) of `The.Housemaid.2025.S26e_g2p*`
(E32, the passing workflow: 0.36 serious/h, 6.12 noticeable/h). Merged by cue. `hits` = how many
of the 4 audits flagged the cue. Harold judged these errors not significant (2026-10-20); they
are kept as the first test set for the phrasebank. Regenerate: `python make_residuals.py`.

| cue | hits | sev | confirmed | kind | English | our Greek | auditor suggestion |
|---|---|---|---|---|---|---|---|
| 1747 | 4 | 3 | 3 | joke | You know, the teapot. | Ξέρεις, με την τσαγιέρα. | Κι αν γλυκάνω το παιχνίδι; Ξέρεις, σαν την τσαγιέρα. |
| 620 | 4 | 2 | 0 | unnatural | God, and how about those roots? | Θεέ μου, και τι λες γι' αυτή τη ρίζα; | Θεέ μου, και οι ρίζες της; Τι λες; |
| 1347 | 4 | 2 | 0 | unnatural | but your roots are making a break for it. | αλλά η ρίζα σου έχει αρχίσει / να φαίνεται. | αλλά τα ριζάρια σου πάνε να ξεμυτίσουν. |
| 1382 | 4 | 2 | 0 | meaning | Andy, it's locked. | Άντι, είναι κλειδωμένα. | Άντι, είναι κλειδωμένο. |
| 1535 | 4 | 2 | 0 | unnatural | I think that would only make things worse for me. | Νομίζω πως αυτό μόνο χειρότερα / θα κάνει τα πράγματα για μένα. | Νομίζω ότι θα χειροτέρευε μόνο τα πράγματα για μένα. |
| 1057 | 3 | 2 | 0 | meaning | But I don't really eat meat. | Αλλά δεν τρώω και πολύ κρέας. | Αλλά δεν τρώω κρέας, ουσιαστικά. |
| 1618 | 3 | 2 | 0 | unnatural | I'll be watching. | Θα βλέπω. | Θα σε παρακολουθώ. |
| 1805 | 3 | 2 | 0 | unnatural | ...should've seen the look on the Frenchmen's faces when 23 rampaged... | ...έπρεπε να βλέπατε τα μούτρα / των Γάλλων όταν 23 μαινόμενοι... | ...να είχατε δει τα μούτρα / των Γάλλων όταν 23 μαινόμενοι... |
| 242 | 2 | 2 | 0 | unnatural | - Where are they? - Where are what? | -Πού είναι; / -Πού είναι ποια; | -Πού είναι; / -Τι πράγμα; |
| 590 | 2 | 2 | 0 | tone | Stay the fuck away from my husband. | Μείνε μακριά απ' τον άντρα μου! | Κράτα τα χέρια σου μακριά από τον άντρα μου, γαμώτο. |
| 893 | 2 | 2 | 0 | unnatural | No, I can't have you do that. | Όχι, δε μπορώ να σας βάλω να το κάνετε. | Όχι, δεν γίνεται να το κάνετε αυτό. |
| 937 | 2 | 2 | 0 | unnatural | to do really boring shit. | για να κάνω τέρμα βαρετές μαλακίες. | για να κάνω απίστευτα βαρετές μαλακίες. |
| 11 | 1 | 2 | 0 | unnatural | I'm just going to say, I think you might be overqualified for this job | Θα σου πω απλώς ότι μάλλον / έχεις υπερβολικά προσόντα | Θα σου πω ότι μάλλον είσαι υπερκατάλληλη για τη δουλειά |
| 114 | 1 | 2 | 0 | unnatural | I knew she wouldn't call. | Το 'ξερα ότι δεν θα έπαιρνε. | Το 'ξερα ότι δεν θα τηλεφωνούσε. |
| 158 | 1 | 2 | 0 | unnatural | that has to be a barn burner, | που πρέπει να τα σπάει, | που πρέπει να είναι εκπληκτική, |
| 165 | 1 | 2 | 0 | tone | Yeah, you look better without them. | Ναι, είσαι πιο όμορφη χωρίς αυτά. | Ναι, σου πάνε περισσότερο χωρίς αυτά. |
| 173 | 1 | 2 | 0 | register | Hello. | Γεια σας. | Γεια. |
| 189 | 1 | 2 | 0 | unnatural | turn this dinner for three into a dinner for four. | να κάνουμε το δείπνο για τρεις / για τέσσερις. | να μετατρέψουμε το δείπνο για τρεις / σε δείπνο για τέσσερις. |
| 216 | 1 | 2 | 0 | unnatural | And then if I could just get a key for the deadbolt. | Και αν γινόταν να έχω ένα κλειδί / για τον σύρτη. | Και αν μπορώ να έχω ένα κλειδί / για την κλειδαριά ασφαλείας. |
| 238 | 1 | 2 | 0 | unnatural | Shit. | Σκατά. | Γαμώτο. |
| 247 | 1 | 2 | 0 | unnatural | Bullshit! | Μαλακίες! | Ψέματα! |
| 263 | 1 | 2 | 0 | unnatural | Where's my nail at? | Πού πήγε το νύχι μου; | Πού έπεσε το νύχι μου; |
| 288 | 1 | 2 | 0 | unnatural | um, Mercury in retrograde. | ε, ο ανάδρομος Ερμής. | Δεν σε είχα για τύπο / των αστρολογικών χαρτών. |
| 483 | 1 | 2 | 0 | unnatural | Not a root in sight. Is... | Ούτε ίχνος ρίζας. Είναι... | Ούτε μία ρίζα στα μαλλιά. Είναι... |
| 503 | 1 | 2 | 0 | register | -I'll leave you alone. -No, no. Please. | -Θα σας αφήσω. / -Όχι, σε παρακαλώ. | -Θα σ' αφήσω ήσυχο/η. / -Όχι, όχι. Σε παρακαλώ. |
| 519 | 1 | 2 | 0 | unnatural | What about you? You... your, um... | Εσένα; Οι... ε... | Εσένα; Οι γονείς σου / τους αρέσουν τα παιχνίδια; |
| 971 | 1 | 2 | 0 | unnatural | I don't suppose you feel sober enough to drive us home? | Φαντάζομαι δεν είσαι αρκετά ξεμέθυστος / για να οδηγήσεις ως το σπίτι; | Δε φαντάζομαι να είσαι αρκετά νηφάλιος / για να μας πας σπίτι; |
| 1192 | 1 | 2 | 0 | unnatural | I've had enough of that asshole. | Ως εδώ με δαύτον τον μαλάκα. | Μου 'χει query τα νεύρα αυτός ο μαλάκας. |
| 1515 | 1 | 2 | 0 | unnatural | with zero chance at custody. | με μηδέν πιθανότητες / για την επιμέλεια. | χωρίς καμία πιθανότητα για την επιμέλεια. |

Notes:

- 1746-47 is one pun: "Maybe I can sweeten the pot? / You know, the teapot." Our Greek:
  «Κι αν βάλω κι άλλα στο τραπέζι; / Ξέρεις, με την τσαγιέρα.» The pun is lost.
- 620 and 1347: singular «η ρίζα» for hair roots; maybe a false positive.
