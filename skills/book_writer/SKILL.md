# book_writer

## Description
Guided multi-phase book writing: outline → storyline → chapter-by-chapter writing with verification → final consistency review and polish.

## Parameters
- topic: book title or topic (required)
- language: writing language, "zh" or "en" (default: auto-detect from user's language)
- style: writing style — "novel", "academic", "technical", or "tutorial" (default: "novel")
- num_chapters: approximate number of chapters (required)
- target_audience: who this book is for (required)

## Example
run_skills("book_writer", {"topic": "The Art of Programming", "language": "en", "style": "technical", "num_chapters": 12, "target_audience": "junior developers"})

## Output directory

Create all files in a subdirectory named after the topic (sanitized: lowercase, underscores for spaces):

```
<project>/<topic_slug>/
├── outline.md
├── storyline.md
├── chapter_01_<title>.md
├── chapter_02_<title>.md
├── ...
└── review_report.md
```

## Phase 1: Outline (outline.md)

Create outline.md with these sections:

```
# <Book Title> — Outline

## Basic Info
- Title: ...
- Language: ...
- Style: ...
- Estimated Chapters: ...
- Target Audience: ...

## Chapter Structure
1. Chapter 1: <chapter title> — <one-line summary>
2. Chapter 2: <chapter title> — <one-line summary>
...

## Core Themes
- Theme 1: ...
- Theme 2: ...

## Writing Principles
- Principle 1: ...
- Principle 2: ...
```

**Verify**: After writing outline.md, check:
- All chapters form a logical progression
- No missing critical topics
- Chapter count matches or reasonably approximates num_chapters
- Topic coverage is complete
- Tell the user what you found and confirm before proceeding

## Phase 2: Storyline (storyline.md)

Create storyline.md with these sections:

```
# <Book Title> — Storyline

## Main Arc
(Describe the main plot arc from beginning to end)

## Chapter Pacing
- Chapters 1-3: <phase description> (setup / introduction)
- Chapters 4-7: <phase description> (development / conflict)
- ...

## Key Turning Points
1. Turning point 1 (Chapter X): ...
2. Turning point 2 (Chapter Y): ...

## Characters / Core Concepts
(For novels: characters with traits and arcs)
(For technical books: key concepts introduced per chapter)
```

**Verify**: After writing storyline.md, check:
- Storyline is fully consistent with outline.md chapter structure
- Pacing is reasonable — no rushed or dragged sections
- Key turning points are well-placed
- Tell the user what you found and confirm before proceeding

## Phase 3: Chapter Writing (chapter_XX_<title>.md)

Write chapters one at a time. Each chapter file must include:

```
# Chapter X: <chapter title>

## Summary
(2-3 sentences summarizing this chapter)

[main content]

## Key Points
- Point 1
- Point 2
```

**Chapter-by-chapter verification** — after writing EACH chapter, check:
1. Consistency with outline.md — does this chapter deliver what the outline promised?
2. Consistency with storyline.md — does this chapter fit the pacing and arc?
3. Transition check — are there contradictions with the PREVIOUS chapter? (For chapter 1, skip this)
4. Read the previous chapter's ending and ensure this chapter follows naturally
5. If issues found, fix immediately before moving on

**Multi-chapter consistency check (every 5 chapters)** — after chapters 5, 10, 15, etc.:
- Re-read the last 3-5 chapters at a glance
- Check for character/terminology drift
- Check timeline continuity
- Report findings to user

## Phase 4: Final Consistency Review (review_report.md)

After ALL chapters are written, create `review_report.md` and perform these checks:

### A. Timeline Consistency
- List all events with approximate timeline markers from every chapter
- Flag any chronological contradictions
- Fix any found issues in the relevant chapter files

### B. Character / Terminology Consistency
- For novels: extract all character names, verify consistent traits, actions, and relationships across chapters
- For technical books: extract all key terms, verify consistent definitions and usage
- Flag and fix any drift

### C. Plot Hole / Logic Gap Check
- Trace the main argument/storyline across all chapters
- Flag any leaps in logic, unexplained events, or missing connections
- Fix or add bridging content as needed

### D. Tone and Style Consistency
- Sample the opening and closing of 3 random chapters
- Check for tone shifts (formal ↔ casual, academic ↔ conversational)
- Normalize where needed

### E. Chapter Transition Quality
- Read the last 2 paragraphs of chapter N and first 2 paragraphs of chapter N+1 for all N
- Ensure smooth transitions; flag abrupt jumps
- Fix weak transitions

### F. Optimization
- Identify the weakest chapter (thinnest content, weakest arguments, or poorest flow)
- Propose specific improvements and implement them
- Final pass: read the first chapter and last chapter — confirm they form a satisfying arc

### G. Final Report (review_report.md)
Write a structured report covering all checks above, with:
- Summary of findings (OK / issues found / fixed)
- Per-chapter status
- Recommendations for the user (e.g., areas that may need human review)

## Completion

Tell the user the book is complete. Report:
- Total chapters written
- Total word count (approximate)
- Review findings summary
- Location of all output files
