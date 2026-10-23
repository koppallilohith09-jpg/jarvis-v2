# Speech component notices and source locations

- Kokoro-82M model and voice data: Apache-2.0. https://huggingface.co/hexgrad/Kokoro-82M
- kokoro-onnx 0.6.1: MIT. https://github.com/thewh1teagle/kokoro-onnx
- ONNX Runtime: MIT. https://github.com/microsoft/onnxruntime
- NumPy: BSD-3-Clause. https://github.com/numpy/numpy
- Phonemizer: GPL-3.0. https://github.com/bootphon/phonemizer
- eSpeak NG: GPL-3.0-or-later. https://github.com/espeak-ng/espeak-ng
- espeakng-loader 0.2.4: source and bundled platform loader at https://github.com/thewh1teagle/espeakng-loader

The model/runtime licence texts accompany the bundled model resources. Installed package metadata and licence files are retained by the collection rules. The JARVIS integration source is provided in this project under native/backend and native/src; the exact Python dependency versions are recorded in backend/requirements.lock.txt. This build has no application telemetry opt-in and explicitly disables ONNX Runtime telemetry before creating the inference session.
