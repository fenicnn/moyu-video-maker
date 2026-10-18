# Moyu Studio vocabulary contract

## Vocabulary format

```json
{
  "schemaVersion": 2,
  "vocabulary": [{
    "cueIndex": 1,
    "term": "worth it",
    "phonetic": "/ˈwɜːθ ɪt/",
    "partOfSpeech": "phrase",
    "meaning": "值得"
  }]
}
```

`cueIndex` must be an integer. Studio matches entries with `cueIndex + normalized(term)`. The pipeline only produces this format, with `schemaVersion` fixed at `2`.

## Highlight parsing parity

Mirror `pc/macos/src/shared/srt.ts`:

- recognize `<font color=...>` and `<span style="...color: ...">`;
- accept quoted/unquoted attributes and named, hex, or functional CSS colors;
- strip nested tags and decode HTML entities;
- retain a highlighted value only when it contains Latin letters and Latin count is at least CJK count;
- deduplicate only within each cue using NFKC, lowercase English, straight apostrophes, collapsed whitespace, and trim;
- never deduplicate the same normalized term across different cues: each occurrence in a later cue remains highlighted and produces its own `cueIndex + term` vocabulary entry;
- classify a line containing CJK as Chinese context; otherwise a line containing Latin letters is English context.

## Import diagnostics

- “版本不受支持”: update Studio to a build that supports the vocabulary format above.
- “字幕序号或词汇不匹配”: verify numeric cue index and normalized term.
- Partial imports usually mean Pipeline and Studio extracted different highlighted terms; run the fixture tests first.
