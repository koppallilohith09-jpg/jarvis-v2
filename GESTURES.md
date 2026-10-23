# Local gestures for JARVIS

Personal adaptation of FatihMakes/Mark-LVI. Original attribution and CC BY-NC 4.0 license retained.

Run `JARVIS-Local-Gestures.exe`. Open **Modes > Hand gestures**. You can also use `Start-Gestures.cmd` to run only the gesture panel and pairing dashboard, without the conversational assistant.

There is a separate **Gesture View** window. It opens when a camera session starts; **Open separate Gesture View** reopens it. PC mode displays mirrored local video with a hand-joint overlay and the recognized pose. iPad mode displays only received hand landmarks on the PC. The view states whether Windows control is on or whether it is preview only. Closing the view stops camera/control; its Stop button does the same. Opening the view by itself does not start a camera.

For pointer control, check **Allow gestures to move/click/scroll** before starting the PC webcam. If hand joints appear but the pointer does not move, check the view's control status. Camera/model errors appear there and in `logs/desktop.log`. If the selected camera is black or unavailable, stop and choose a different PC camera number in the panel. The app tries Windows' DirectShow backend if the default backend cannot open it.

Simple launch commands such as “open YouTube” and “open Notepad” route directly to the existing action tools, without an AI round trip. “Open” by itself asks for a target. Windows app launching resolves installed executables, shortcuts or Store app IDs and no longer types into desktop search. Offline hearing and voice warm up before listening; stale microphone audio is bounded and dropped during transcription.

The default is preview: hand detection runs but cannot send Windows input. Check **Allow gestures to move/click/scroll** before starting if you want control. Stop before switching sources. Closing the panel or quitting stops control. Camera access never starts automatically.

| Hand pose | Action |
| --- | --- |
| Index finger extended | Move the primary-screen pointer |
| Thumb/index pinch held 150 ms | One left click; release to click again |
| Index and middle fingers | Move up/down to scroll |
| Fist held 700 ms | One media play/pause; release to repeat |
| Open palm | Pause input |

The physical mouse corner failsafe stops Windows input on the next gesture action. A missing hand resets pending gestures. Invalid, replayed, unpaired and expired remote frames are rejected. Input exceptions disarm control. This is a heuristic hand-pose controller; lighting, hand angle and model accuracy affect recognition.

## PC webcam

Select **Start PC webcam**. Windows Settings → Privacy & security → Camera must allow desktop apps to use the camera. Close other apps holding the default webcam. Detection uses MediaPipe locally. Video is not uploaded by this gesture feature.

## iPad camera, including away from home

Install Tailscale on the iPad and sign in to the same tailnet as the PC. The PC must remain powered on and connected. Use the private HTTPS hostname reported by your running app after pairing is configured.

After explicitly approving private remote access, run `Enable-iPad.ps1` from the portable app folder. It configures private Tailscale Serve to forward HTTPS to `http://127.0.0.1:8000` on the PC, enables `dashboard_enabled` and sets `dashboard_external_url` to your private HTTPS `.ts.net` URL. Restart the app. The server listens only on loopback; no router port forwarding is needed. Keep Tailscale Funnel off. This exposes the paired dashboard's assistant commands and file-transfer functions to authorized devices on your tailnet; guard the pairing code and use a tailnet access policy limited to your devices.

Choose **Remote Control** in the PC app to create a pairing code. In gestures-only mode, choose **Show iPad pairing code**. On the iPad open the private HTTPS address, enter the code, then tap **Gestures**. On the PC select **Arm paired iPad camera**. On the iPad tap **Start iPad camera** and allow Safari to use its camera. The PC webcam is not required for iPad mode.

The hand model and WASM are served from the PC, with no CDN requests from the gesture page. Inference runs on the iPad; 21 hand landmark triples are AES-GCM encrypted and sent through the paired dashboard. Hiding the page, stopping the camera or losing the connection stops capture. Both devices have a Stop button. Only one camera source controls a session.

## Development and checks

`python prepare_local.py` explicitly downloads the hand model and pinned MediaPipe JS 0.10.21 inference assets, verifies the npm package SHA-512 integrity and records asset SHA-256 hashes. Python inference uses MediaPipe 0.10.32. These versions precede the 1.x release whose upstream privacy notice adds usage metrics.

`python -m unittest test_gestures test_local_privacy -v` checks gesture timing, preview permissions, stop/failsafe behavior, encryption/authentication and source compilation. `python launcher.py --self-test` checks Qt panel construction, real local hand inference on a blank frame and local Kokoro speech synthesis without opening a camera or controlling the mouse. These checks do not establish physical-camera accuracy or test a real iPad.

Keep the EXE beside its `_internal`, `models` and `core` folders. It is a portable app folder, not a single self-contained file. `Check-App.cmd` creates `diagnostics.json`; startup errors go to `logs/desktop.log`.

Version 1.8 contains no offline AI model or Ollama runtime. Connect your own Gemini or OpenAI key for AI answers. Gesture-only mode, direct commands, local speech and memory work independently of that connection. Returning a hand after leaving the frame anchors at the current pointer position without a jump. Precise, Balanced and Fast profiles adjust sensitivity and smoothing.
