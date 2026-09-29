# Labelling guide

You're creating the **"correct answers"** that Nazar's models are scored against. Accuracy numbers mean nothing without human labels, so this step is what turns "it seems to work" into "it's 78% accurate on Hindi".

**File:** `evaluation/datasets/labels.csv`. Open it in Excel or Google Sheets; Hindi displays correctly.
**Time:** about 1 hour (sentiment ~30–40 min, names ~25–30 min).
**Rows:** 150 articles (75 English, 75 Hindi). 50 of them also need names.

Fill in only these columns and don't change the others:

| Column | Fill in for | What to write |
|---|---|---|
| `sentiment` | **all 150 rows** | `positive`, `neutral` or `negative` |
| `entities` | rows where `label_entities` = **yes** (50 rows) | the names mentioned, separated by `;` |
| `notes` | optional | anything odd ("text is cut off", "not really news") |

**Judge only the `title` and `text` shown**, not what you know from elsewhere, and not the full article. The models are scored on exactly this text.

Save as **CSV UTF-8** when you're done. In Excel: *File → Save As → "CSV UTF-8 (Comma delimited)"*. Plain "CSV" breaks the Hindi.

---

## 1. Sentiment: what's the tone of the text?

Ask: **"Does this text read as good news, bad news, or plain reporting?"**

| Label | When | Examples |
|---|---|---|
| `negative` | conflict, accusations, protests, failures, threats, criticism | "Congress demands CEC's arrest" · "CJP threatens nationwide protests" · "राहुल गांधी का CEC पर बड़ा हमला" |
| `positive` | success, agreement, praise, relief, good outcomes | "Trade deal between India and US done & dusted" · "Voter verification completed smoothly" |
| `neutral` | factual reporting, explainers, announcements, schedules | "How can a CEC be removed? Rules explained" · "EC postpones two outreach events" · "दिल्ली में वेरिफिकेशन पूरा" |

Tips:
- **The text's tone, not your opinion of it.** An article reporting an accusation is `negative` even if you think the accusation is unfair.
- **Mixed text:** pick the dominant tone. If truly balanced, `neutral`.
- **Don't overthink it.** Spend about 10–15 seconds per row. Your first instinct is usually the right label.

## 2. Entities: which names appear?

Only for the 50 rows marked `label_entities = yes`. List the **people, organisations and places** named in the title and text:

| Include | Examples |
|---|---|
| People | Gyanesh Kumar, Rahul Gandhi, चिराग पासवान |
| Organisations | Election Commission, Congress, BJP, Supreme Court, CJP, Indian Express |
| Places / countries | Delhi, West Bengal, India, कोलकाता |

**Don't include** policies or ideas (SIR, tariffs, trade deal, "vote chori"), job titles on their own ("the CEC", "minister"), dates, or numbers.

**How to write them:**
- Separate names with `;`, for example: `Gyanesh Kumar; Election Commission; Rahul Gandhi; Delhi`
- **Either language is fine.** Write the name as it appears (`राहुल गांधी`) or in English (`Rahul Gandhi`); both are matched to the same person.
- List each name **once**, even if it appears several times.
- Use the **fullest form** that appears: `Sukhbir Singh Sandhu`, not `Sandhu`.
- If there are **no names at all**, write `none`. Don't leave it blank: blank means "not labelled yet".

---

## When you're done

Tell Claude, or run:

```bash
uv run python -m evaluation.run_eval
```

This writes `evaluation/results/report.md`, which shows how often each model agrees with your labels, broken down by language and compared with a simple baseline.

It's fine to label in several sittings: save as you go, and the evaluation uses whatever rows are filled in.
