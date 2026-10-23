# JARVIS 1.8.2 — Windows portable

App launches now watch for a visible matching Windows window, including reused
processes and Store app child windows. A process starting alone does not prove
the app opened. Confirmed completion and unverified results are announced through
local speech without another cloud model request.

Supported native browsers use read-only foreground address-bar accessibility to
check the requested tab URL. This confirms an open tab, not a loaded page.
Managed browser sessions additionally inspect navigation, the final URL and HTTP
response before reporting a page loaded. Redirects are reported separately.
Unsupported or unavailable browser evidence is reported as unverified.

Includes the 1.8.1 scoped cloud DNS fix and camera timestamp/session fixes. No
offline language model or Ollama runtime is included. Speech recognition,
speech synthesis, camera detection and SQLite memory run locally. AI chat and
document analysis use the cloud provider selected in Settings.

The friend edition starts without the creator's keys, settings, chats, uploaded
files or memory. Enter your own Gemini/OpenAI key. Provider quota and charges
depend on your account. Extract the entire ZIP and keep the support folders
beside the EXE.

The personal edition retains its private Echo reference scene and credits. The
friend edition uses the original JARVIS interactive globe. The modified private
Echo assets are excluded from the friend ZIP. All included component licenses
and notices remain applicable.

Verification uses mocked app/browser adapters and speech output, plus packaged
checks for the application, cloud adapters, camera worker races and WebGL scene.
No real webcam, microphone, pointer actions or private browser tabs are used by
these checks. Physical gesture accuracy and webcam eye calibration still depend
on the device and environment; webcam gaze remains experimental.
