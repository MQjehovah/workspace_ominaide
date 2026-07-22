from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from core.auth.dependencies import get_current_user
from core.auth.jwt import create_access_token, decode_access_token
from core.config.settings import settings
from plugins.remote.backend import service as remote_service

router = APIRouter(prefix="/api/remote", tags=["remote"])
ws_router = APIRouter(tags=["remote"])


class OnlineRequest(BaseModel):
    device_id: str
    name: str
    room_id: str


class PairRequest(BaseModel):
    device_id: str
    room_id: str


class HeartbeatRequest(BaseModel):
    device_id: str


VIEWER_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no'><title>OmniAide Remote</title><style>body{margin:0;background:#000;overflow:hidden;touch-action:none}video{width:100vw;height:100vh;object-fit:contain}#bar{position:fixed;top:8px;left:8px;color:#fff;font:13px sans-serif;background:rgba(0,0,0,.5);padding:4px 8px;border-radius:6px;z-index:10}</style></head><body><div id='bar'>连接中…</div><video id='v' autoplay playsinline></video><script>
const params=new URLSearchParams(location.search);const code=params.get('code');
const v=document.getElementById('v'),bar=document.getElementById('bar');
let pc=null;let dc=null;let ended=false;
function send(ev){if(dc&&dc.readyState==='open'){try{dc.send(JSON.stringify(ev));}catch(e){}}}
function btn(b){return b===2?'right':b===1?'middle':'left';}
function norm(e){return v.clientWidth>0?e.offsetX/v.clientWidth:0;}
function normY(e){return v.clientHeight>0?e.offsetY/v.clientHeight:0;}
v.addEventListener('mousemove',e=>send({type:'mouseMove',x:norm(e),y:normY(e)}));
v.addEventListener('mousedown',e=>{e.preventDefault();send({type:'mouseDown',button:btn(e.button)});});
v.addEventListener('mouseup',e=>send({type:'mouseUp',button:btn(e.button)}));
v.addEventListener('wheel',e=>{e.preventDefault();send({type:'wheel',deltaY:e.deltaY});},{passive:false});
v.addEventListener('contextmenu',e=>e.preventDefault());
function touchNorm(t){const r=v.getBoundingClientRect();return {x:(t.clientX-r.left)/r.width,y:(t.clientY-r.top)/r.height};}
v.addEventListener('touchstart',e=>{e.preventDefault();const p=touchNorm(e.touches[0]);send({type:'mouseMove',x:p.x,y:p.y});send({type:'mouseDown',button:'left'});},{passive:false});
v.addEventListener('touchmove',e=>{e.preventDefault();const p=touchNorm(e.touches[0]);send({type:'mouseMove',x:p.x,y:p.y});},{passive:false});
v.addEventListener('touchend',e=>{e.preventDefault();send({type:'mouseUp',button:'left'});},{passive:false});
function ignored(c){return c==='F5'||c==='F11'||c==='F12';}
document.addEventListener('keydown',e=>{if(e.code&&!ignored(e.code)){e.preventDefault();send({type:'keyDown',code:e.code});}});
document.addEventListener('keyup',e=>{if(e.code&&!ignored(e.code)){e.preventDefault();send({type:'keyUp',code:e.code});}});
let ws;
function wsSend(m){if(ws&&ws.readyState===1)ws.send(JSON.stringify(m));}
fetch('/api/remote/pair/'+code).then(r=>r.ok?r.json():Promise.reject(new Error('code'))).then(d=>{
  pc=new RTCPeerConnection({iceServers:d.iceServers||[{urls:'stun:stun.l.google.com:19302'}]});
  pc.ontrack=e=>{v.srcObject=e.streams[0];bar.textContent='已连接（可控制）';setTimeout(()=>v.focus(),200);};
  pc.onicecandidate=e=>{if(e.candidate)wsSend({type:'ice',payload:e.candidate});};
  const wsUrl=(location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/remote/'+d.room_id+'?token='+encodeURIComponent(d.guest_token);
  ws=new WebSocket(wsUrl);
  ws.onopen=()=>{bar.textContent='等待被控端授权…';wsSend({type:'requestControl',name:navigator.userAgent.includes('Mobile')?'手机':'浏览器'});};
  ws.onmessage=async ev=>{const m=JSON.parse(ev.data);
    if(m.type==='controlAllowed'){dc=pc.createDataChannel('input');pc.addTransceiver('video',{direction:'recvonly'});const offer=await pc.createOffer();await pc.setLocalDescription(offer);wsSend({type:'offer',payload:offer});bar.textContent='等待画面…';}
    else if(m.type==='controlDenied'){ended=true;bar.textContent=m.reason==='busy'?'被控端忙':'被控端拒绝';}
    else if(m.type==='revoked'){ended=true;bar.textContent='被控端断开了控制';}
    else if(m.type==='answer'){await pc.setRemoteDescription({type:'answer',sdp:m.payload.sdp});}
    else if(m.type==='ice'){try{await pc.addIceCandidate(m.payload);}catch(e){}}
  };
  ws.onclose=()=>{if(!ended)bar.textContent='连接已断开';};
}).catch(()=>{bar.textContent='配对码无效或已过期';});
</script></body></html>"""


@router.post("/online")
async def online(req: OnlineRequest, user: dict = Depends(get_current_user)):
    remote_service.register_device(user["id"], req.device_id, req.name, req.room_id)
    return {"ok": True}


@router.delete("/online")
async def offline(user: dict = Depends(get_current_user)):
    remote_service.clear_user_devices(user["id"])
    return {"ok": True}


@router.get("/devices")
async def devices(user: dict = Depends(get_current_user)):
    return {"devices": remote_service.list_devices(user["id"])}


def _ice_servers() -> list:
    import json
    try:
        return json.loads(settings.webrtc_ice_servers)
    except Exception:
        return [{"urls": "stun:stun.l.google.com:19302"}]


@router.get("/ice")
async def ice_config(user: dict = Depends(get_current_user)):
    return {"iceServers": _ice_servers()}


@router.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest, user: dict = Depends(get_current_user)):
    remote_service.heartbeat(req.device_id)
    return {"ok": True}


@router.post("/pair")
async def create_pair(req: PairRequest, user: dict = Depends(get_current_user)):
    code = remote_service.create_pair(user["id"], req.device_id, req.room_id)
    return {"code": code}


@router.get("/pair/{code}")
async def consume_pair(code: str):
    room_id = remote_service.consume_pair(code)
    if not room_id:
        raise HTTPException(status_code=410, detail="Pair code invalid or expired")
    guest_token = create_access_token({"sub": 0, "guest_room": room_id}, timedelta(minutes=30))
    return {"room_id": room_id, "guest_token": guest_token, "iceServers": _ice_servers()}


@router.get("/viewer", response_class=HTMLResponse)
async def viewer(code: str):
    return VIEWER_HTML


@ws_router.websocket("/ws/remote/{room_id}")
async def remote_websocket(websocket: WebSocket, room_id: str):
    token = websocket.query_params.get("token")
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        return
    guest_room = payload.get("guest_room")
    if guest_room and guest_room != room_id:
        await websocket.close(code=4003)
        return

    await websocket.accept()
    await remote_service.room_join(room_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            await remote_service.room_broadcast(room_id, websocket, message)
    except WebSocketDisconnect:
        pass
    finally:
        await remote_service.room_leave(room_id, websocket)
