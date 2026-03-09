# Media Library

The library contains ready-made assets the AI agent can reference in the composition timeline.
All files are maintained by the project owner — the AI reads but does not modify this directory.

## Structure

```
library/
├── index.json          ← Master index (edit to add/remove assets)
├── memes/              ← Static image memes (.png / .jpg)
├── sfx/                ← Sound effects (.mp3)
├── stickers/           ← Animated stickers (.gif)
├── cutaways/           ← Short video cutaway clips (.mp4)
└── music/              ← Background music tracks (.mp3)
```

## index.json schema

```jsonc
{
  "memes":    [ <LibraryItem>, ... ],
  "sfx":      [ <LibraryItem>, ... ],
  "stickers": [ <LibraryItem>, ... ],
  "cutaways": [ <LibraryItem>, ... ],
  "music":    [ <LibraryItem>, ... ]
}
```

### LibraryItem fields

| Field         | Type            | Required | Description                                      |
|---------------|-----------------|----------|--------------------------------------------------|
| `id`          | string          | ✅       | Unique identifier used in timeline references    |
| `path`        | string          | ✅       | Relative path from `library/` directory          |
| `kind`        | string          | ✅       | `image` / `audio` / `gif` / `video`             |
| `tags`        | string[]        | ✅       | Searchable keywords                              |
| `description` | string          | ✅       | Human-readable description for AI context        |
| `duration`    | number (s)      | —        | Duration for audio/video/gif assets              |
| `bpm`         | integer         | —        | Beats per minute (music only)                    |
| `mood`        | string          | —        | Mood tag (music only): focused / energetic / etc.|

## How to add assets

1. Drop the file into the correct category subfolder.
2. Add an entry in `index.json` with a unique `id`.
3. The agent will pick it up on the next tool call (no restart needed).

## Using library assets in the timeline

```
# In the agent's timeline tools:
vlog_timeline_add_meme(project_id, lib_id="meme_this_is_fine", ...)
vlog_timeline_add_sfx(project_id, lib_id="sfx_success", ...)
vlog_timeline_add_music(project_id, lib_id="mus_lofi_focus", ...)
vlog_timeline_add_sticker(project_id, lib_id="stk_rocket", ...)
vlog_timeline_add_cutaway(project_id, source="library", lib_id="cut_terminal_run", ...)

# Search the library:
vlog_library_search(query="баг ошибка", category="memes")
vlog_library_list(category="music")
```

## Asset naming conventions

- Memes:    `meme_<short_name>`   — e.g. `meme_this_is_fine`
- SFX:      `sfx_<short_name>`    — e.g. `sfx_success`
- Stickers: `stk_<short_name>`    — e.g. `stk_rocket`
- Cutaways: `cut_<short_name>`    — e.g. `cut_terminal_run`
- Music:    `mus_<short_name>`    — e.g. `mus_lofi_focus`
