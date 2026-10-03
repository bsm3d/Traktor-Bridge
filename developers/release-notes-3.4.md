# Traktor Bridge 3.4

## New
- Cue colours on the CDJ: hot cues now carry a colour (cue blue, load aqua, loop green for
  Traktor, the nearest of the 8 rekordbox colours when the source gives one).
- A music folder is a source: File > Open a music folder (Ctrl+Shift+O). Each folder becomes a
  playlist, title, artist, bpm and key come from the tags (mp3, aiff, wav, flac, m4a).
- File > New playlist (Ctrl+N): drop audio files or folders on its list, or use Add files, then
  sort, reorder and set cues. Save as M3U8 keeps the playlist as a file.

## Good to know
- A music folder has no beatgrid: it is laid from 0 ms when the tags give a bpm.
- Reloading the collection drops a playlist made by hand, save it as M3U8 first.
- The CDJ keys still need the player files of your own rekordbox, imported once in Options > CDJ.
- Verified: an export made with 3.3 and one made with 3.4 differ only by the cue colour bytes.
