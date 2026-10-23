# JARVIS V2

Windows desktop voice assistant with hand gestures, local speech recognition and synthesis, local memory, file tools, and an interactive 3D globe. This repository publishes the **full friend edition of JARVIS 1.8.2**. V2 is the distribution name; the underlying application version remains 1.8.2.

[Download JARVIS V2 for Windows x64](https://github.com/Srisathvikchebrolu/jarvis-v2/releases/latest/download/jarvis-v2.zip)

## Install

1. Extract the **entire** downloaded `jarvis-v2.zip` to a writable folder.
2. Open `JARVIS-1.8.2-Friend` and run `JARVIS-Local-Gestures.exe`. Keep its support folders beside the EXE.
3. Open Settings and connect **your own Gemini or OpenAI API key**. Chat and document analysis require an internet connection and available provider quota. OpenAI API billing is separate from a ChatGPT subscription.

Windows native voice and Kokoro British voice are included. See [README-FIRST.txt](README-FIRST.txt) for settings and command examples. This full download is about 1.39 GB. The smaller [JARVIS V1](https://github.com/Srisathvikchebrolu/jarvis-v1) is based on build 1.8 and provides Kokoro as a separate optional download.

## Features and limits

- Type commands or hold Hold to talk while speaking, then release to send.
- Use local Whisper recognition, Windows/Kokoro speech, hand detection, and SQLite memory. There is **no offline language model or Ollama runtime**.
- App completion announcements check for a visible matching Windows window. Supported native browsers can confirm the foreground tab URL; managed browser sessions can also verify navigation loaded. Missing accessibility evidence is reported as unverified.
- Includes scoped cloud DNS and camera timestamp/session fixes from 1.8.1. See [RELEASE-1.8.2.md](RELEASE-1.8.2.md) for verification details and limitations.
- Use Modes > Hand gestures to start the camera and enable Windows pointer control. Index finger moves; pinch clicks; two raised fingers and vertical motion scroll; open palm pauses. Ctrl+Alt+G stops input.
- Rotate and zoom the original JARVIS globe. iPad access requires separate private HTTPS pairing.
- Webcam eye tracking is experimental; head-assisted pointer control is available. Physical camera accuracy depends on the device and environment.

## Privacy

The friend package excludes the creator's keys, settings, chats, uploads, and memory. A new local profile is created on your computer. When cloud AI is connected, your requests and relevant file or memory content are sent to the selected provider. Camera and local speech processing run on your computer. Review the provider's data terms before connecting.

## Source and attribution

The `source/` directory contains the integration source shipped with the release, including its dependency lists and build scripts. Large application libraries, models, and runtime assets are distributed through Releases, not Git. A source checkout alone is not the complete portable application; use the release for the ready-to-run build.

This is a modified integration based on [FatihMakes/Mark-LVI](https://github.com/FatihMakes/Mark-LVI), licensed **CC BY-NC 4.0**. Attribution is required and commercial use is not permitted under that license. [Holo Gestures](https://github.com/zubair-trabzada/holo-gestures) components retain their MIT license. The friend edition uses original JARVIS globe scene code with the three.js runtime; private Brahma reference scene assets are excluded. Other included components retain their own licenses.

See [LICENSE](LICENSE), [UPSTREAM.json](UPSTREAM.json), [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt), and the retained component notices.
