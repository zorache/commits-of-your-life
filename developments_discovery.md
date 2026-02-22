# Discovery of Events — Development Notes

The MVP asks users to explicitly journal their timeline. But most people don't have that ready. What they have is scattered: Obsidian vaults, dream diaries, text files, snapshots of their world tucked away across years. This document explores how to *discover* life events from existing personal archives, rather than requiring the user to narrate them from scratch.

The README's own words frame this well:

> "In a world bombarded with information, I'm curious what it could look like to more mindfully surface one's own notes and diaries. Instead of scrolling through content designed to hook you, sitting with tokens from your past selves."

Discovery isn't just a technical problem. It's the core artistic question: **can AI help you find the story you've already been writing?**

---

## The Two Modes

### Mode 1: Interaction Mode (the mirror)

A reflective, conversational space for probing your personal archive. You bring a current thought, feeling, or question — the system surfaces resonant fragments from your past writing. The value is the *process*, not the output.

This is not a search engine. It's a dialogue with your past selves.

```
You, now                          Your archive
    │                                 │
    │  "I keep thinking about         │
    │   the year I left home"         │
    │ ──────────────────────────────► │
    │                                 │
    │         ◄──── echoes ────────── │
    │                                 │
    │  2020-03-14  "the apartment     │
    │   is empty now..."              │
    │  2019-11-30  "talked to mom     │
    │   about the plan..."            │
    │  2021-01-15  "a year later      │
    │   and I still..."               │
    │                                 │
    │  (sit with them)                │
    │  (probe again)                  │
    │  (or walk away)                 │
```

**Key properties:**
- No pressure to produce anything. You can probe, read, and close the tab
- Each session is shaped by what you're feeling *today* — the same archive surfaces differently depending on what you ask
- The echoes are presented as fragments, not summaries — your own words, not AI's interpretation
- Multiple probes in a session build a conversation, not a queue

**What it is not:**
- Not a chatbot — the system doesn't talk *to* you, it reflects *back* at you
- Not a search tool — results are selected for resonance, not relevance
- Not a step in a pipeline — interaction mode is complete in itself

---

### Mode 2: Commits of Your Life (the artifact)

The git repository. A concrete, downloadable timeline of life events rendered as version history. This is the *output* — something you keep, share, revisit.

```
* e4a2f1b  2024-01-15  Start therapy
* 8c3d9e0  2023-06-01  Quit the startup
* 1f7a2b3  2022-09-20  Move to the coast
│
│ * a3b4c5d  2021-03-01  First real grief
│ * 9d8e7f6  2020-11-15  Lose someone
│/
* 2b3c4d5  2020-03-14  Leave home
* 7e8f9a0  2019-09-01  Start college
* 0a1b2c3  2001-06-15  Born in summer
```

**How it gets built — three input pathways:**

1. **From interaction mode (curated):** During a probe session, the user selects echoes that feel like life events. These become commits. The timeline grows through reflection — each commit is a conscious choice about what matters.

2. **From auto-inference (generated):** With enough data, the system scans the full archive and infers a timeline — date clusters, emotional shifts, recurring themes appearing or vanishing. This produces a "first draft" of your life repo. Ghost commits that the user can confirm, edit, or dismiss.

3. **From manual journaling (narrated):** The existing MVP. User writes a block of text about their life, agents parse it into events. Direct storytelling.

These pathways aren't exclusive. A user might:
- Auto-generate a skeleton from their vault
- Use interaction mode to probe gaps and add curated events
- Journal to fill in periods they didn't write about at the time

**The git graph as layered artifact:**

```
Ghost commits (inferred)     ░░░░░░░░░░░░░░░░░░░░░░░░░░░░
                             the system's guess at your timeline
                             faint, suggested, unconfirmed

Curated commits (probed)     ████████████████████████████████
                             events you discovered through reflection
                             confirmed through interaction mode

Narrated commits (journaled) ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
                             events you told directly
                             from the manual journaling MVP
```

The ghost layer gives you instant visual density — you see the shape of your life immediately. But the real timeline is what you've chosen to claim. The distinction between "the system found this" and "I confirmed this matters" is preserved in the artifact.

---

### How the modes relate

```
┌──────────────────────┐         ┌──────────────────────┐
│   Interaction Mode   │         │  Commits of Your Life │
│   (the mirror)       │ ──────► │  (the artifact)       │
│                      │ curate  │                       │
│   probe              │         │  git repo             │
│   echo               │         │  timeline             │
│   reflect            │         │  download             │
│   probe again        │         │  share                │
│                      │         │                       │
│   value: process     │         │  value: product       │
└──────────────────────┘         └───────────────────────┘
        ▲                                 ▲
        │                                 │
   you bring a feeling              also fed by:
   it brings back your words        - auto-inference
                                    - manual journaling
```

Interaction mode *can* feed commits, but doesn't have to. Commits *can* come from interaction mode, but also from other sources. The modes are complementary, not sequential. You might use interaction mode for years without ever generating a repo. You might generate a repo without ever probing.

**The separation matters because:**
- Forcing reflection to produce output changes the nature of the reflection
- A timeline that *only* comes from auto-inference misses the curation that gives it meaning
- A timeline that *only* comes from probing misses events you wouldn't think to ask about
- The richest artifact comes from all three pathways layered together

---

## Approach 1: Probe-Based Discovery (Recommended)

Instead of "upload your vault and wait," the interaction is a dialogue with your past selves.

### How it works:

1. **Ingest** — User points the system at a folder (or Obsidian vault). Files get chunked and embedded once.
2. **Probe** — User enters a current thought, feeling, or desire. "I've been thinking about leaving the city." "I feel like I'm becoming someone new." "What did I believe about love?"
3. **Retrieve** — System finds resonant past entries via semantic search.
4. **Surface** — Past entries are presented as echoes, not search results. The user sits with them.
5. **Commit** — User selects which surfaced moments become life events. Or the LLM synthesizes them into candidate events.
6. **Iterate** — Multiple probes, each adding to the timeline. The git repo grows through conversation.

### Why this fits the project:

- Aligns with "creative probing of a current thought, feeling, or desire"
- **The user is an active participant in discovery, not a passive consumer of extraction**
- **Each probe is itself an act of reflection — the tool shapes the process of remembering**
- No correct answer — **the "same" vault could produce different repos depending on what the user is thinking about today**

### UX sketch:

```
┌─────────────────────────────────────────────────┐
│  Commits of Your Life                           │
│                                                 │
│  [Archive loaded: 847 notes, 2019–2026]         │
│                                                 │
│  What's on your mind?                           │
│  ┌─────────────────────────────────────────┐    │
│  │ I keep circling back to the year I      │    │
│  │ moved away from home                    │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  ── echoes from your archive ──                 │
│                                                 │
│  2020-03-14  "the apartment is empty now..."    │
│  2020-04-02  "first morning waking up to..."    │
│  2019-11-30  "talked to mom about the plan..."  │
│  2021-01-15  "a year later and I still..."      │
│                                                 │
│  [ ✓ ] 2020-03-14 → "Leave home"               │
│  [ ✓ ] 2020-04-02 → "First morning in new..."  │
│  [   ] 2019-11-30                               │
│  [ ✓ ] 2021-01-15 → "Reflect on first year..." │
│                                                 │
│  [Add to timeline]   [Probe again]              │
│                                                 │
│  ── your timeline so far: 12 commits ──         │
└─────────────────────────────────────────────────┘
```

---

## Approach 2: Temporal Skeleton + Fill

A more mechanical but reliable approach. Good as a complement to probe-based discovery.

### How it works:

1. **Scan** every document for temporal markers: explicit dates, "January 2021," "last summer," "when I was 22," file modification timestamps, Obsidian daily note titles.
2. **Build a timeline skeleton** — a rough chronological index of when things were written / what they reference.
3. **Cluster** temporally-close entries.
4. **Summarize** each cluster into candidate life events using LLM.
5. **Present** the full timeline for user curation.

### Strengths:
- Produces a complete timeline without user effort
- Catches things the user might not think to probe for
- Good for "give me a first draft of my life repo"

### Weaknesses:
- Less reflective / artistic
- May surface mundane entries alongside significant ones
- Date inference from text is noisy

### Implementation notes:
- Regex patterns for date extraction: `\d{4}[-/]\d{1,2}[-/]\d{1,2}`, `(January|February|...) \d{4}`, `(spring|summer|fall|winter) \d{4}`, `when I was \d+`
- File metadata: `mtime`, `ctime`, Obsidian YAML frontmatter `date:` fields
- Obsidian daily notes follow `YYYY-MM-DD.md` naming convention — free temporal data

---

## Approach 3: Semantic Drift as Branches

This is the most artistically interesting approach. Instead of extracting events, detect *shifts in who the person is*.

### How it works:

1. Embed all notes chronologically.
2. Compute semantic drift over time — how the embedding centroid shifts month to month.
3. Large drift = major life change = branch point.
4. Cluster each "era" (between drift points) by theme.
5. Generate commit messages that capture the evolution, not just the events.

### Example output:
```
main:       birth ─── childhood ─── high school ───┐
                                                    │
career:                                             ├── college ─── first job ─── startup
                                                    │
inner-life:                                         └── grief ─── therapy ─── "I'm okay"
```

### Why this is compelling:
- Branches aren't based on *what happened* but on *who you became*
- The "drift" is the story — the moments where your language changed
- Maps beautifully to git's model: branches as divergent paths of self

### Technical approach:
- Sliding window of embeddings over time
- Cosine distance between consecutive windows
- Peaks in distance = branch candidates
- Topic modeling (BERTopic or LLM-based) within each era for branch naming

---

## Technical Architecture

### Ingestion Pipeline

```
Source Folder (Obsidian vault / text files)
    │
    ├── File walker
    │   - Recursively find .md, .txt files
    │   - Respect .gitignore / .obsidianignore
    │   - Skip binary, images (for now)
    │
    ├── Metadata extraction
    │   - File timestamps (created, modified)
    │   - Obsidian frontmatter (YAML)
    │   - Obsidian tags (#tag) and links ([[link]])
    │   - Daily note date from filename
    │
    ├── Chunking
    │   - Short notes (<500 tokens): keep as single chunk
    │   - Long notes: split on headers (##, ###)
    │   - Preserve note title and metadata per chunk
    │   - Chunk overlap: ~50 tokens for context continuity
    │
    └── Embedding + Storage
        - Embed each chunk
        - Store in vector DB with metadata
        - Build temporal index (date → chunk IDs)
```

### Embedding choices

| Option | Pros | Cons |
|--------|------|------|
| **OpenAI `text-embedding-3-small`** | Good quality, cheap, fast | Requires API key, data leaves machine |
| **Voyage AI `voyage-3-lite`** | High quality for retrieval | API dependency |
| **Local: `nomic-embed-text`** | Fully local, no data leaves machine | Requires `ollama` or similar |
| **Local: `all-MiniLM-L6-v2`** | Tiny, fast, well-known | Lower quality for nuanced personal text |
| **Anthropic embeddings** | Stay in one ecosystem | Not available yet as product |

**Recommendation:** Default to a local model (`nomic-embed-text` via `ollama`) for privacy alignment with the project's ethos. Offer OpenAI as opt-in for better quality.

### Vector store choices

| Option | Pros | Cons |
|--------|------|------|
| **ChromaDB** | Simple, Python-native, persistent | Limited scale |
| **FAISS** | Fast, battle-tested | No metadata filtering natively |
| **LanceDB** | Embedded, good metadata support | Newer |
| **SQLite + `sqlite-vss`** | Zero dependency, embedded | Less mature |
| **Just numpy** | No dependencies at all | Manual everything |

**Recommendation:** ChromaDB for the prototype. It handles metadata filtering (dates, tags), persistence, and is pip-installable. For a hackathon/art project, simplicity wins.

### Retrieval strategy

Hybrid retrieval matters here because personal notes are messy:

1. **Semantic search** — cosine similarity on embeddings (the core RAG query)
2. **Temporal filtering** — restrict to date ranges ("tell me about 2020")
3. **Keyword boost** — exact string matches for names, places, specific terms
4. **Recency weighting** — optional: slightly prefer entries closer to a referenced time
5. **Diversity sampling** — avoid returning 5 chunks from the same note; spread across time

**Re-ranking:** After initial retrieval (top-k=20), use the LLM to re-rank by relevance to the probe. This is expensive but worth it for quality — we're making an art piece, not a search engine.

---

## Integration with Existing Pipeline

The discovery system produces the same output format the MVP agents expect:

```python
# Discovery output → same shape as MVP agent output
[
    {
        "commit_message": "Leave home for the first time",
        "date": "2020-03-14",
        "description": "From your note 'empty apartment': the day you moved out...",
        "is_major_change": True,
        "source_files": ["2020-03-14.md", "reflections/moving.md"],  # new field
    },
    ...
]
```

The `source_files` field is new — it traces each life event back to the original notes, maintaining provenance. This matters both for trust and for the art: the commit description could include fragments of original writing.

The git repo generation (`create_life_repo` in `app.py`) doesn't need to change. Discovery is a new *input pathway* that feeds the same downstream pipeline.

---

## What Goes in the Commit Files

In the MVP, `event_001.md` files contain a title, date, and AI-generated description. With discovery, we can do something richer:

```markdown
# Leave home for the first time

Date: 2020-03-14

---

From your notes:

> "the apartment is empty now and I can hear the highway for the first
> time. I didn't think silence could sound so different."
> — 2020-03-14.md

> "talked to mom about the plan. she said she knew this was coming.
> I don't know if that makes it easier."
> — 2019-11-30.md

---

You were 21. This was the beginning of what your later notes call
"the year everything shifted."
```

The commit file becomes a *curated artifact* — fragments of original writing, stitched together with AI-generated connective tissue. The git repo isn't just a timeline; it's an anthology.

---

## Open Questions

1. **How much curation vs. automation?** The probe-based model is high-curation (user drives). The temporal skeleton is high-automation. The right answer is probably both: auto-generate a skeleton, then let the user probe to refine and add.

2. **What about non-text?** Photos with EXIF dates, voice memos, screenshots. These are powerful memory triggers. Vision models could caption images; whisper could transcribe audio. But scope creep is real — start with text.

3. **Incremental updates?** If the user adds new notes to their vault, the system should be able to update embeddings incrementally rather than re-processing everything. ChromaDB supports upsert by ID.

4. **Multi-vault / multi-source?** People's digital lives span many tools. Obsidian, Apple Notes, Google Docs, text messages. Each would need a source adapter. Start with local markdown files.

5. **The "forgetting" question.** Git never forgets — every commit is permanent. But some things in personal archives are meant to be let go. Should there be a way to `git rm` from your life repo? Or is permanence the point? ("nothing is deleted, only committed to" — from the README)

6. **Privacy and local-first.** The README frames this as a tool, not a platform. All embedding and retrieval should be local-first. The only API call should be the LLM synthesis step (which already exists in the MVP). Embeddings stay on-device.

---

## Suggested Implementation Order

### Phase 1: Ingestion (foundation for both modes)
- File walker for markdown/text files
- Chunking with metadata extraction
- Embedding with ChromaDB storage
- Simple CLI to ingest a folder: `python discover.py ingest ~/obsidian-vault`

### Phase 2: Interaction Mode — core loop
- Semantic search given a probe
- Surface echoes — raw fragments, not summaries
- Present as a reflective interface, not search results
- No commit generation yet — just the mirror
- CLI: `python discover.py probe "what did I believe about love?"`

### Phase 3: Interaction Mode → Commits bridge
- User selects echoes that feel like life events
- LLM synthesizes selected fragments into candidate commits
- Output in the same format as MVP agent pipeline
- The curation step: "this echo matters, make it a commit"

### Phase 4: Auto-inference (ghost commits)
- Date extraction from text + metadata
- Auto-generate timeline skeleton from full archive
- Present as ghost commits — suggested, unconfirmed
- User can confirm ghosts into real commits, or dismiss them
- Gap detection: "you have no notes between 2021-06 and 2022-01 — what happened?"

### Phase 5: Web UI — two modes
- Interaction mode page: probe input → echoes → sit with them → optionally curate
- Commits page: git graph with layered commits (ghost / curated / narrated)
- Toggle or tab between modes
- Integrate all three input pathways into a single timeline

### Phase 6: Semantic Drift (experimental)
- Chronological embedding analysis
- Drift detection for branch points
- Era labeling and theme extraction
- This is the most speculative but most artistically compelling feature

---

## Dependencies to Add

```
chromadb>=0.4.0          # vector store
sentence-transformers    # local embeddings (if not using ollama)
# OR
ollama                   # local LLM + embeddings via ollama
```

Minimal addition to the existing stack. ChromaDB is the main new dependency.

---

## Relation to the Art

The MVP is a *transcription tool* — you tell your story, it formats it as git.

Discovery makes it a *mirror* — your past writing reflects back at you, recontextualized. The probe is the question you bring to the mirror. The echoes are what the mirror shows. The git repo is the story you choose to tell after looking.

This is closer to the README's vision: "AI could help us understand ourselves better. To have the autonomy over our own evolution, and to tell our own stories."

The discovery system doesn't tell your story for you. It helps you find it.
