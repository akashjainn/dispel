# Wizard voice lines

Short ElevenLabs text-to-speech clips the wizard and witch say at big moments
(`app/src/renderer/voice.js`). They are the one kind of audio allowed in git
(AGENTS.md): generated UI sounds, not recordings of anyone.

| Character | ElevenLabs voice | Voice ID | Model |
|---|---|---|---|
| wizard | Maverick - Commanding and Powerful (Voice Library) | `V33LkP9pVLdcjeB2y5Na` | `eleven_multilingual_v2`, stability 0.4, style 0.4 |
| witch | Dispel Snarky Witch (designed in Israel's account) | `aZctzuTomsuiAlDigGh3` | `eleven_v3` |

## When each line plays

| File | When | Text |
|---|---|---|
| `drop` | a file is dropped | Ooh, a file. Let me stir the cauldron... |
| `reveal`, then one `snark1-3` | file is likely synthetic | Wait... WAIT! Ha! Gotcha! Likely synthetic! |
| `snark1` | | Nice try, robot. |
| `snark2` | | Did you really think I wouldn't notice? Please. |
| `snark3` | | Somebody's voice got photocopied. Badly. |
| one of `real1-3` | file is likely real | |
| `real1` | | Relax. Likely real. The cauldron is bored. |
| `real2` | | Likely a real human. How refreshing. |
| `real3` | | Nothing spooky here. Likely real. Carry on, mortal. |
| `unsure` | file is inconclusive | Hmm. Can't tell. Even my cauldron is shrugging. |
| one of `cast1-2` | "Yes, hang up" spell fires | BEGONE! / Hang up THIS! |
| one of `gone1-2` | after the call window shatters | Poof. That caller's gone. You're welcome. / And STAY gone! |

Nothing plays while idle, hovering, or listening to a call, and call verdicts
are silent (only the hang-up speaks). Lines say "likely synthetic" / "likely
real", never "fake" or "real" as a certainty (AGENTS.md copy rules).

## Changing a line

Generate the new text with the same voice and model (ElevenLabs web app, API,
or the ElevenLabs MCP server), save it as `<character>/<file>.mp3`, and update
the table above. A missing clip is skipped silently, so a new line needs no
code change unless it adds a new moment.
