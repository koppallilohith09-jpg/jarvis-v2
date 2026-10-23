const token=sessionStorage.getItem('jarvis_token'), secret=sessionStorage.getItem('jarvis_key');
const video=document.querySelector('#video'), status=document.querySelector('#status'), start=document.querySelector('#start'), camera=document.querySelector('#camera');
let stream=null, detector=null, aes=null, running=false, preparing=false, generation='', seq=0, lastVideoTime=-1, cancelled=0;
if(!token||!secret) location.replace('/login');
const tell=text=>{status.textContent=text;};
async function request(url,options={}) {
  const response=await fetch(url,{...options,headers:{'Authorization':`Bearer ${token}`,'Content-Type':'application/json'},signal:AbortSignal.timeout(5000)});
  const body=await response.json();
  if(!response.ok) throw new Error(body.error||`Request failed (${response.status})`);
  return body;
}
async function encrypt(payload) {
  if(!aes) {
    const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(secret),'PBKDF2',false,['deriveKey']);
    aes=await crypto.subtle.deriveKey({name:'PBKDF2',salt:new TextEncoder().encode('JARVIS-DASHBOARD-v1'),iterations:200000,hash:'SHA-256'},key,{name:'AES-GCM',length:256},false,['encrypt']);
  }
  const nonce=crypto.getRandomValues(new Uint8Array(12));
  const ct=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv:nonce},aes,new TextEncoder().encode(JSON.stringify(payload))));
  const bytes=new Uint8Array(nonce.length+ct.length);bytes.set(nonce);bytes.set(ct,12);
  return btoa(String.fromCharCode(...bytes));
}
function release() {
  running=false; cancelled++;
  if(stream)stream.getTracks().forEach(track=>track.stop());
  stream=null;video.srcObject=null;start.disabled=false;camera.disabled=false;
  if(detector)detector.close();detector=null;
}
async function stop(message='Camera and PC gestures stopped.') {
  release();tell(message);
  try{await request('/api/gestures/stop',{method:'POST',keepalive:true});}catch{}
}
async function loop() {
  try {
    if(!running)return;
    if(video.readyState>=2 && video.currentTime!==lastVideoTime) {
      lastVideoTime=video.currentTime;
      const result=detector.detectForVideo(video,performance.now());
      const landmarks=(result.landmarks[0]||[]).map(p=>[Math.max(0,Math.min(1,p.x)),Math.max(0,Math.min(1,p.y)),Math.max(-2,Math.min(2,p.z))]);
      const enc=await encrypt({landmarks,generation,seq:seq++});
      if(!running)return;
      const reply=await request('/api/gestures',{method:'POST',body:JSON.stringify({enc})});
      if(running)tell(landmarks.length?`Connected · ${reply.gesture||'looking for gesture'}`:'Connected · No hand visible');
    }
    if(running)setTimeout(loop,80);
  } catch(error){await stop(`Stopped: ${error.message}`);}
}
start.addEventListener('click',async()=>{
  if(preparing||running)return;
  preparing=true;start.disabled=true;camera.disabled=true;
  const attempt=++cancelled;
  try {
    if(!isSecureContext||!navigator.mediaDevices)throw new Error('Camera needs your private HTTPS address.');
    const state=await request('/api/gestures/status');
    if(state.mode!=='remote')throw new Error('First arm the paired iPad camera in the PC Gestures panel.');
    generation=state.generation;seq=0;lastVideoTime=-1;tell('Loading local hand tracker…');
    const {HandLandmarker,FilesetResolver}=await import('/gesture-assets/vision_bundle.mjs');
    const files=await FilesetResolver.forVisionTasks('/gesture-assets/wasm');
    const tracker=await HandLandmarker.createFromOptions(files,{baseOptions:{modelAssetPath:'/gesture-assets/hand_landmarker.task',delegate:'CPU'},runningMode:'VIDEO',numHands:1,minHandDetectionConfidence:.7,minTrackingConfidence:.7});
    if(attempt!==cancelled){tracker.close();return;}detector=tracker;
    const capture=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:camera.value},width:{ideal:640},height:{ideal:480}},audio:false});
    if(attempt!==cancelled){capture.getTracks().forEach(t=>t.stop());return;}
    stream=capture;video.srcObject=stream;await video.play();
    if(attempt!==cancelled)return;
    stream.getVideoTracks()[0].addEventListener('ended',()=>stop('Camera was disconnected.'));
    running=true;tell(state.control?'Windows input enabled. Open palm pauses.':'Preview only. Enable Windows input on the PC to control it.');loop();
  }catch(error){await stop(`Stopped: ${error.message}`);}
  finally{preparing=false;if(!running){start.disabled=false;camera.disabled=false;}}
});
document.querySelector('#stop').addEventListener('click',()=>stop());
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop('Stopped because this page is hidden.');});
window.addEventListener('pagehide',()=>{release();fetch('/api/gestures/stop',{method:'POST',headers:{Authorization:`Bearer ${token}`},keepalive:true}).catch(()=>{});});
