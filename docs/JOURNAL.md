# Nazar project journal

A plain-language record of building Nazar: **what we saw, why it happened, what we changed, and what we learned.** Technical words are in **bold** the first time and explained in the [glossary](#glossary) at the end.

Entries are in the order things happened. Numbers are real measurements from our runs, not estimates, unless marked otherwise.

---

## What Nazar does, in one picture

```
 news feeds (English + Hindi)
        │  1. COLLECT    read ~30 Indian news feeds, keep stories about the topic
        ▼
 ~130 articles
        │  2. CLEAN      remove duplicates, broken text, other languages
        ▼
        │  3. UNDERSTAND embeddings (meaning as numbers), sentiment, people/organisations
        ▼
        │  4. GROUP      put articles telling the same storyline together → narratives
        ▼
        │  5. MEASURE    growth, sentiment, English vs Hindi share, timeline, evidence
        ▼
        │  6. WRITE      the LLM names each narrative and writes the brief (with sources)
        ▼
 dashboard + intelligence brief
```

---

## Entry 1: Setting up on a real laptop

**What we saw**
- The C: drive had **0 GB free**, and installing Python packages failed with "not enough space on the disk".
- Docker Desktop was installed but wouldn't start.
- The laptop has 16 GB of RAM and a 6 GB GPU. Background installs were stopped by Claude Code when memory ran critically low.

**What we changed**
- All downloads and caches (Python packages, AI models) live on the E: drive inside the project (`.cache/`, `data/models/`).
- The database is **SQLite** (a single file, nothing to install) instead of PostgreSQL in Docker. The code keeps the door open: pointing one setting (`DATABASE_URL`) at Postgres + **pgvector** switches over, whether Postgres runs in Docker or in a hosted service like Neon or Supabase.
- Big installs run one package at a time to keep memory use low.

**What we learned**
- A **virtual environment** keeps a project's packages separate from other projects. It does **not** separate memory or disk: it still uses the same RAM and drive as everything else.
- Tiny setup details (a full drive, a broken Docker) can block a project for hours. Choosing a simpler tool (SQLite) and moving on was the right call for a first version.

---

## Entry 2: GDELT kept refusing us

**What we saw**
- **GDELT**, the planned news source, returned **HTTP 429** ("too many requests") almost every time, even for **the very first request after many hours of silence**.
- A tip from GDELT's GitHub suggested adding a browser-like **User-Agent**. We tested it: with 20–50 seconds between requests, *both* the browser User-Agent and ours were refused. So that wasn't our problem.

**Why it happened (most likely)**
- GDELT limits requests per public internet address (**IP address**). Many Indian internet providers put many customers behind one shared address (**CGNAT**), so other people's requests count against "us". GDELT has also become much stricter for everyone.
- Our own code was polite: 2–3 requests per run, 10 seconds apart. (Our very first test requests *were* too close together and probably triggered the first cooldown. That's a lesson about testing gently.)

**What we changed**
- The default news source became **publisher RSS feeds**: 19 English and 11 Hindi Indian outlets. Each outlet is a separate website, so there's no single gatekeeper that can refuse us.
- The GDELT code is kept and tested but switched off (`NEWS_SOURCES=rss`).

**What we learned**
- Free public APIs can be unreliable in ways you can't control. A demo shouldn't depend on one.
- RSS is lightweight: a run downloads about 15–30 MB and stores under 1 MB.
- The trade-off: RSS only shows each outlet's **latest stories (about 1–3 days)**, and only from the outlets we chose. **Our choice of outlets shapes what narratives can appear**, which is a form of **selection bias** that must be stated.

---

## Entry 3: Finding the right articles (keyword matching)

**What we saw**
- For "India-US trade negotiations", our first keyword filter matched an oil-price story (because of "*traders*") and Trump–Xi summit stories (because "*Washington*" counted as "United States").
- Even after fixing that, only about **5–6 truly relevant articles** existed in 3 days: the topic simply wasn't big news that week.
- The feeds' most common words showed the big story was the **Election Commission / CEC Gyanesh Kumar controversy** (about 44 English and 35 Hindi headlines in 3 days).

**What we changed**
- Topic words expand into both languages using a name list (**gazetteer**) and a small word list (**lexicon**): "US" also matches अमेरिका, "trade" also matches व्यापार.
- A word only matches its own forms (trade, trades, traded), not related words (traders). City names aren't treated as countries.
- Multi-word names are recognised as one unit ("Election Commission", "Gyanesh Kumar"), and a **named person counts double**, because naming someone is strong evidence a story is on-topic.
- The demo topic became the Election Commission story: **88 matching articles, all on-topic**.

**What we learned**
- Nazar can only find narratives that exist. The demo topic must be something **currently in the news**.
- Keyword matching is a first, loose filter (it aims for high **recall**). Later steps make it precise.

---

## Entry 4: Hindi text broke in quiet ways

**What we saw**
1. **37 of 128 articles were thrown away as "malformed"**, and only 12 Hindi articles survived out of about 31.
2. Hindi names were cut short: "राहुल गांध" instead of "राहुल गांधी", "बीजेप" instead of "बीजेपी".
3. Keywords included "है।" (with the Hindi full stop stuck on).

**Why it happened**
- Hindi vowel signs (like ा, ी, ु) are **combining marks** in **Unicode**. Python doesn't count them as "letters", and its regular expressions treat them as non-word characters. So:
  1. our "is this text mostly letters?" check thought normal Hindi headlines were junk;
  2. our "trim punctuation from the ends of a name" step trimmed the final vowel sign;
  3. the **danda** (।, the Hindi full stop) sits in the same Unicode block as Hindi letters, so it was glued onto words.

**What we changed**
- Letters are now "letters **or** combining marks" everywhere text is checked or trimmed; the danda is excluded from words. After the fix: **47 Hindi articles, 0 dropped**, and full names.

**What we learned**
- Tools built and tested mostly on English can fail silently on Indian scripts. **Test with real Hindi text.** Every one of these bugs was invisible until we looked at real output.

---

## Entry 5: The Hindi entity model

**What we saw**
- The planned Hindi **NER** model (IndicNER) is **gated**: Hugging Face requires an account that accepts its terms.
- An open alternative (**HiNER**, from IIT Bombay, built on Google's **MuRIL**) loaded fine but **found zero names**. Looking inside, the **tokenizer** turned every Hindi word into `[UNK]` (unknown).

**Why it happened**
- That model's repository ships an **empty vocabulary** (5 entries instead of about 197,000), so it couldn't read any Hindi.

**What we changed**
- The HiNER model is paired with the real tokenizer of the model it was built from (MuRIL). Names are grouped at word level (`aggregation_strategy="first"`) so they aren't split mid-word.
- Result: it finds राहुल गांधी, चिराग पासवान, ज्ञानेश कुमार, दिल्ली, कांग्रेस.
- Key people in the story (Gyanesh Kumar, Chirag Paswan, CJP…) were added to the name list, so the English and Hindi versions of a name count as **one** entity.

**What we learned**
- "The model loaded without errors" doesn't mean it works. **Look at what it outputs.**
- Model repositories can be incomplete. Knowing how a model was built (its base model) helps fix it.

---

## Entry 6: Narratives were splitting by language

**What we saw**
- The first real run found 5 groups, but they were split **by language**. The CJP resignation ultimatum appeared twice: once as an English group and once as a Hindi group.

**Why it happened**
- The **multilingual embedding model** (bge-m3) puts both languages in the same space, but every Hindi text still carries a shared "this is Hindi" direction. Two articles in the same language looked closer than the same story in two languages.

**What we changed**
- Before grouping, we subtract each language's **average embedding** (**language centering**). This removes the shared "language direction" and keeps what makes stories different.
- The grouping algorithm (**HDBSCAN**) now uses **"leaf" selection**, which keeps fine-grained storylines instead of one big blob.
- Articles left ungrouped join the nearest narrative **only if** they're as close to it as that narrative's own members.

**Result:** 9–13 narratives per run, nearly all mixing English and Hindi (e.g. CJP ultimatum: 11 English + 8 Hindi articles).

**What we learned**
- Multilingual models aren't perfectly language-neutral. A simple, well-known correction fixed it.
- Clustering settings matter a lot: the same data gave 2, 5 or 9 groups depending on them.

---

## Entry 7: What is a narrative, exactly?

**The question:** should a narrative be "Mr. Raj / Ms. Pooja", or "the argument over the budget"?

**The answer**
- A **topic** is what you monitor ("the budget controversy").
- **Entities** are who's involved (Raj, Pooja, the Finance Ministry).
- A **narrative** is **a storyline or claim that several sources repeat**, a *sentence about what is being said*: "Raj says the budget ignores the middle class", or "Pooja accuses Raj of misleading voters".

**What we saw:** titles like "Paswan / Chirag / चाहिए". These were placeholders (the three most distinctive words) because the LLM wasn't connected yet. The group itself *was* a real narrative: *an NDA ally urging the CEC to answer the opposition firmly.*

**What we changed:** until the LLM is connected, a narrative's title is its **most representative headline** (the one closest to the group's centre), which is readable and honest. The LLM replaces it with a narrative statement.

**What we learned / limits**
- Grouping by meaning finds *storylines*. Two articles about the same event with **opposite framing** can still land together. Detecting framing is the optional **stance detection** extension.

---

## Entry 8: A "narrative" made of unrelated articles

**What we saw**
- "India-US trade negotiations", Hindi only, last 24 hours: 5 articles matched (a Trump–Xi meeting, Trump–Xi's wine, Rajnath Singh on terror and trade, Captain Amarinder on the BJP). Nazar showed them as **one narrative with "+300% growth"**, which was misleading.

**Why it happened**
1. The relevance score (how similar each article is to the topic) was calculated but not used as a filter.
2. With fewer than 10 articles, grouping was skipped and **everything was lumped into one group**.

**What we tried, with numbers**
- *A single relevance cut-off:* failed. Good Hindi articles scored as low as 0.45, and the junk scored 0.44–0.46. Comparing short topic phrases with whole articles is too blunt.
- *A Hindi version of the topic:* barely helped (junk still up to 0.50).
- *Requiring the headline itself to match:* dropped 15 good articles.
- ***Group tightness (cohesion):*** worked. Real narratives had an average article-to-article similarity of **0.57 or more**; the junk group had **0.45**.

**What we changed**
- A narrative needs **at least 3 articles** and **cohesion ≥ 0.52**.
- A light relevance floor (0.33) removes clearly unrelated articles.
- When nothing qualifies, the run finishes with **"Not enough coverage"** and shows where the articles went. The same India-US test now says: *"4 relevant articles were found, but they don't share a common storyline."*

**What we learned**
- Saying "nothing substantial found" honestly is a feature, not a failure. The thresholds were set from only two runs, so they're **provisional** and must be re-checked in evaluation.

---

## Entry 9: Memory and speed

**What we saw**
- One run got stuck for over 10 minutes with only 2 GB of RAM free. The process had grown to 4.7 GB.
- Runs took about 80 seconds even when little had changed.

**Why it happened**
- The embedding model was loaded **twice** per run. Python doesn't give memory back to Windows promptly, so the second load pushed the laptop into **swapping** (using the disk as memory), which is extremely slow.
- Timing each step showed **loading was the slow part, not computing**:

| Step (154 articles) | Time |
|---|---|
| Load embedding model (first time) | 57 s |
| **Embed 154 articles** | **3.7 s** |
| Load sentiment model | ~5 s |
| Sentiment for 153 articles | 1.9 s |
| Load entity models | 8.4 s |
| Entities for 153 articles | 6.7 s |

**What we changed**
- One copy of each model per process, shared by all steps.
- **`KEEP_MODELS_LOADED=true`:** the server keeps models loaded between runs (uses about 2.5 GB of GPU memory).
- The compiled code for the clustering library is cached on disk.
- The "is the LLM online?" check took 4.3 s on Windows (the `localhost` name tries IPv6 first, and Windows retries a closed port). Using `127.0.0.1` with a short connect timeout: **0.75 s**.

**Result**

| | Before | After |
|---|---|---|
| First run after starting the server (**cold start**) | ~80 s | ~130 s (loads and caches everything once) |
| Every later run (**warm**) | ~80 s | **~30 s** |
| Topic with no real coverage | misleading narrative | 7 s, honest message |

**What we learned**
- **Measure before optimising.** "Embeddings are slow" felt true but was wrong; loading was the problem.
- On a 16 GB laptop, memory is the main constraint. Close other apps before long runs.

---

## Entry 10: Seeing what's happening (logs)

**What we changed**
- Every run prints stage-by-stage progress with timings to the terminal and to `data/logs/nazar.log`, and ends with a summary. Follow it live:

```powershell
Get-Content data\logs\nazar.log -Wait
```

Example summary (a real run):

```
[run 4] completed (narratives)
    feeds read             30
    headlines              1966
    in time window         1561
    matched the topic      155
    unique after dedup     154
    relevant               152
    narratives             12
    languages              {'en': 100, 'hi': 55}
    time                   ingest 4.2s, enrich 13.1s, analyze 8.5s, name_narratives 4.2s  (total 30.0s)
```

**What we learned**
- The summary answers "where did my articles go?" at a glance. It's how we caught several of the problems above.

---

## Entry 11: Setting up the Oracle server

**What we saw**
- `ssh-keygen -f $HOME\.ssh\…` failed with "No such file or directory". It had been typed in **Command Prompt**, where `$HOME` isn't a variable (that's PowerShell syntax; CMD uses `%USERPROFILE%`).
- The "public IP" toggle was greyed out when the network was created inside the instance form.
- The first attempt picked a 1-core / 1 GB machine, far too small for a language model.
- "Service limits exceeded": this account's free ARM allowance is **2 cores / 12 GB**, not the 4 / 24 we planned for.
- "Out of capacity": Oracle's free ARM machines in the region were all taken.

**What we changed**
- The guide now gives every laptop command for both PowerShell and CMD.
- The network is created first with Oracle's VCN wizard ("Create VCN with Internet Connectivity"), then selected in the instance form.
- The instance is sized at 2 OCPU / 12 GB. Both models still fit; answers are just slower.
- The form was saved as a **stack**, so retrying later is two clicks (Resource Manager → Apply).

**What we learned**
- Free cloud tiers have hidden constraints: per-account limits smaller than the advertised maximum, and busy regions. Plan for waiting and retrying.
- Most setup errors are small (a shell's syntax, a missing toggle). Pasting the exact error message is the fastest route to a fix.

## Entry 12: Measuring quality (evaluation)

**What we built**
- A 150-article labelling set (75 English, 75 Hindi) from real runs, with a plain-language [labelling guide](../evaluation/LABELLING_GUIDE.md), plus scripts that score each model against the labels.

**What we saw while building it**
- **91 of 150 article texts started by repeating the headline**, and some headlines contained `&amp;` instead of `&`. Feeds send HTML codes (**HTML entities**) and our cleaner never decoded them. That was fixed in the pipeline, not just in the dataset.
- **The first clustering results** ([docs/evaluation.md](evaluation.md)): with language centering, **12 of 12** narratives mixed English and Hindi; without it, only **3 of 13**. Nazar's grouping also scored slightly better than a standard baseline (silhouette 0.180 vs KMeans' 0.157).

**What we learned**
- An **ablation** (running the system with one step switched off) is the clearest way to prove a step earns its place.
- Look at the data before labelling it: the headline repeats would have wasted the labeller's time and skewed the scores.
- A low silhouette doesn't have to mean bad clusters. Sub-stories of one event naturally overlap, so we pair it with cohesion and manual checks.

## Entry 13: Switching the LLM to Groq

**What we saw**
- Oracle never had a free ARM machine available: "Out of capacity", night after night. Oracle also halved its free tier in June 2026 (to 2 cores / 12 GB).
- Other free hosts had also tightened (e.g. Hugging Face's free Docker Spaces), and running the LLM on the laptop would tie it up during testing.

**What we changed**
- Narrative naming and the brief now use **Groq**, a hosted API that runs open models (gpt-oss-20b for naming, gpt-oss-120b for the brief). Ollama is still supported with one setting (`LLM_PROVIDER=ollama`).
- Groq's free tier allows about **8,000 tokens per minute**. Our full brief prompt is about 5,600 tokens, and the answer and the model's hidden reasoning need room too, so long prompts are now **trimmed to fit**: evidence excerpts get shorter first, then fewer evidence items per narrative, then the smallest narratives are dropped. On our real run, all 8 narratives and 40 evidence items were kept, with excerpts cut to 120 characters.
- When Groq says "too many requests", Nazar waits the time Groq asks for and tries again.

**What we learned**
- Where the LLM runs doesn't change the ML work: the model still only names narratives and writes the brief, and every claim must still cite evidence.
- Free APIs trade money for limits. Designing for the limit (smaller prompts, waiting politely) is part of the engineering.

---

## Still weak / open questions

- **Hindi sentiment is unreliable.** The sentiment model (trained on tweets) rated many Hindi protest stories as neutral. The evaluation will measure this.
- **Thresholds are provisional:** cohesion 0.52, relevance 0.33, near-duplicate 0.93. All were set from a couple of runs.
- **RSS covers only recent days** and only the outlets we chose.
- **Narrative statements and the brief** need the Oracle LLM server ([setup guide](ORACLE_SETUP.md)).

---

## Glossary

| Term | Plain meaning |
|---|---|
| **API** | A way for one program to ask another for data (e.g. Nazar asking GDELT for articles). |
| **HTTP 429 / rate limit** | "Too many requests." A service limiting how often you can ask. |
| **User-Agent** | A label a program sends to say what it is (e.g. "Chrome" or "python-httpx"). |
| **IP address / CGNAT** | Your internet address. With CGNAT, many customers of a provider share one public address. |
| **RSS feed** | A small file a news site publishes listing its latest stories (title, link, time, summary). |
| **Gazetteer** | Our list of known names in English and Hindi (अमेरिका = US = America → "United States"). |
| **Lexicon** | Our small list of common words in both languages (trade = व्यापार). |
| **Recall / precision** | Recall: how much of what's relevant we found. Precision: how much of what we found is relevant. |
| **Selection bias** | Results shaped by what you chose to look at (here, which outlets). |
| **Deduplication (dedup)** | Removing repeated copies of the same article (same link, same headline, or nearly identical text). |
| **Unicode / combining mark** | Unicode is how computers store every script's characters. A combining mark is a character that attaches to the previous one, like the Hindi vowel signs ा ि ी. |
| **Danda (।)** | The Hindi full stop. |
| **Embedding** | A list of numbers (here, 1,024) that captures a text's meaning. Similar meanings give similar numbers, even across languages. |
| **Cosine similarity** | A score for how close two embeddings are: 1 = same meaning, around 0 = unrelated. |
| **Multilingual model (bge-m3)** | One model that understands many languages and places them in the same "meaning space". |
| **Language centering** | Subtracting each language's average embedding so stories group by meaning, not by language. |
| **Tokenizer / vocabulary / [UNK]** | A tokenizer cuts text into pieces the model knows (its vocabulary). A piece it doesn't know becomes `[UNK]` (unknown). |
| **NER (named-entity recognition)** | Finding names of people, organisations and places in text. |
| **Gated model** | A model you can only download after logging in and accepting its terms. |
| **Sentiment** | Whether a text reads as positive, neutral or negative. |
| **Clustering** | Automatically grouping similar items. Each group here is a candidate narrative. |
| **UMAP** | Squeezes 1,024 numbers per article down to 5 while keeping similar articles close, which makes grouping work better. |
| **HDBSCAN / leaf selection** | The grouping method: it finds dense groups and can leave outliers ungrouped. "Leaf" keeps smaller, finer groups. |
| **Centroid** | The average position of a group, its "centre". |
| **Cohesion** | How similar a group's articles are to each other. Tight group = real storyline. |
| **c-TF-IDF** | A way to pick words that are common in one group but rare in the others (a group's keywords). |
| **Narrative** | A storyline or claim several sources repeat about the event. |
| **Stance detection** | Telling whether an article supports or opposes a claim (an optional extension). |
| **LLM (large language model)** | A model that writes text. Nazar uses it only to name narratives and write the brief, always citing sources. |
| **Ollama** | A program that runs LLMs on a machine and answers requests at a local address. |
| **API / API key** | A way for one program to use another over the internet. The key is a secret password that identifies your account. |
| **Token / rate limit** | Models read and write text in small pieces called tokens (roughly ¾ of an English word). A rate limit caps how many tokens or requests you can use per minute. |
| **Reasoning model** | A model that "thinks" in hidden text before answering. Those hidden tokens count toward its limits. |
| **SSH tunnel** | An encrypted private connection that forwards a port on your laptop to a port on a remote server. |
| **GPU / VRAM** | The graphics card, and its own memory; it runs AI models fast. |
| **RAM / swapping** | The computer's working memory. When it runs out, Windows uses the disk instead (swapping), which is very slow. |
| **Latency / cold vs warm start** | Latency is how long you wait. A cold start includes loading everything; a warm start reuses what's already loaded. |
| **HTML entities** | Codes web pages use for special characters, e.g. `&amp;` for "&". They must be decoded before display. |
| **Ablation** | Running the system with one step switched off, to measure what that step contributes. |
| **Silhouette score** | How much closer items are to their own group than to the nearest other group (-1 to 1; higher = better separated). |
| **Baseline** | A simple reference method (e.g. KMeans, or "always predict the most common label") that a real method should beat. |
| **Macro-F1** | The average F1 score across classes, so rare classes (like "positive") count as much as common ones. |
| **Stack (Oracle Resource Manager)** | A saved recipe for creating cloud resources, re-runnable with one click. |
| **Virtual environment** | A separate folder of Python packages for one project. It doesn't separate memory. |
| **SQLite / PostgreSQL / pgvector** | SQLite is a database in a single file. PostgreSQL is a database server. pgvector adds fast similarity search on embeddings to PostgreSQL. |
