# Traktor Bridge 3.5.1

3.5.1 is a fix release. It contains everything in 3.5, see [release-notes-3.5.md](release-notes-3.5.md).

## Fixes

- **Damaged project files.** A project whose `tracks`, `cues` or `children` was not a list
  stopped the load with an internal error. It is now refused with a message that names the
  problem. A number such as `inf`, `nan` or `1e999` in a project, or a path setting that is not
  text, is dropped and the rest of the project loads.
- **Numbers that are not numbers in collections.** A value written as `inf`, `nan` or `1e999`
  in a Traktor, rekordbox, VirtualDJ, Serato, Mixxx or M3U file could stop the load with an
  internal error, or end up in the playlist as an infinite duration. It is now dropped. A cue or a
  beat grid with such a position is skipped, and a bad cue length means no length.
- **Unknown encoding in an XML file.** A rekordbox or VirtualDJ file that declares an encoding
  Python does not know stopped the load with an internal error. It is now refused with a message
  that names the file. A VirtualDJ playlist with such a label is skipped, and a Traktor file is read
  as UTF-8.
- **Music folders.** A file or folder name holding a superscript digit, such as a superscript
  two, aborted **File > Open a music folder**. The scan now goes on and sorts the name as text.
- **Restoring a backup.** A ZIP that held audio but no `project.json` stopped the restore with
  an internal error. It is now refused with a message. Nothing is written, and the temporary
  folder is removed. The same goes for a ZIP made with a version of the ZIP format that Python
  cannot read.
- **Checksums of a second export.** Exporting twice to the same key could report
  `PIONEER/rekordbox/export.pdb` as different from what was written, when the new file had the
  same size as the old one and was written within 2 seconds. A file written by an export now always
  gets the hash of its own bytes. Only audio left in place keeps the hash of the previous
  checksum file.

## Exports

Exports are unchanged. Playlists, cues and keys are written exactly as in 3.5.

## Validation

The checks on an export do not prove compatibility with every CDJ. Test the exported key on
your player before a gig.

Format details and implementation notes are in [DOCUMENTATION.md](DOCUMENTATION.md).
