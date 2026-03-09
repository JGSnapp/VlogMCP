# Branding Assets

This directory contains the visual identity of the channel.
**All content is set by the administrator. The AI agent reads it but cannot modify it.**

## Structure

```
branding/
├── branding.json              ← Main config (edit this to customise branding)
├── assets/
│   ├── watermark.png          ← Channel logo / watermark overlay (PNG, transparent)
│   └── plates/
│       ├── lower_third.png    ← Lower-third name plate (1920×120 px recommended)
│       ├── section_card.png   ← Section title card (1920×200 px recommended)
│       ├── quote_card.png     ← Quote / highlight card
│       ├── fact_card.png      ← Fact / metric card
│       └── cta_card.png       ← Call-to-action card
└── clips/
    ├── intro.mp4              ← Channel intro clip (prepended automatically at render)
    ├── outro.mp4              ← Channel outro clip (appended automatically at render)
    └── cutaways/
        ├── coffee.mp4         ← "Thinking pause" cutaway
        ├── typing.mp4         ← "Coding" cutaway
        ├── terminal.mp4       ← "Terminal / commands" cutaway
        └── deploy.mp4         ← "Deploy / release" cutaway
```

## How to customise

1. Replace asset files with your own (keep the same filenames, or update `branding.json`).
2. Edit `branding.json` — palette, font sizes, watermark position/opacity, plate coordinates.
3. The renderer and preview engine pick up changes automatically on the next run.

## Notes

- Plate PNG files must be the exact canvas size you want (typically 1920×1080 or sub-regions).
- Watermark is overlaid at full render time; it does **not** appear in preview frames unless you
  render a full project.
- Intro / outro are prepended/appended at render time; they are **not** part of the editable
  composition timeline.
- If an asset file is missing the renderer will log a warning and skip that element gracefully.
