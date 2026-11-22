# Custom music bank (highest priority)

Drop audio files here (or in `flirty/`, `bold/`, `dreamy/` subfolders) and they
are used **before** the CC-BY bank and before any Instagram catalog API.

- Accepted: `.mp3 .m4a .aac .wav .ogg .flac`
- No catalog/API call is made. The file is muxed into the rendered MP4, so the
  same audio is audible everywhere the Reel plays.
- Rotation: least-recently-used first; no track repeats until the pool is
  exhausted. State is stored in `data/engine.db`.
- Caption credit is generated from the filename (`bye (slowed).mp3` →
  `Music: bye slowed`).
- Commit the files so GitHub Actions can use them too.
- Content-ID note: muxing a copyrighted track can still be detected by the
  platform; use material you are allowed to reuse.
