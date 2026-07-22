from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token
from plugins.remote import service as remote_service

router = APIRouter(prefix="/api/remote", tags=["remote"])
ws_router = APIRouter(tags=["remote"])


class OnlineRequest(BaseModel):
    device_id: str
    name: str
    room_id: str


class PairRequest(BaseModel):
    device_id: str
    room_id: str


VIEWER_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>OmniAide Remote</title><style>body{margin:0;background:#000}video{width:100vw;height:100vh;object-fit:contain}#bar{position:fixed;top:8px;left:8px;color:#fff;font:13px sans-serif;background:rgba(0,0,0,.5);padding:4px 8px;border-radius:6px}</style></head><body><div id='bar'>连接中…</div><video id='v' autoplay playsinline></video><script>
const params=new URLSearchParams(location.search);const code=params.get('code');const token=params.get('token')||'';
const v=document.getElementById('v'),bar=document.getElementById('bar');
const pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
pc.ontrack=e=>{v.srcObject=e.streams[0];bar.textContent='已连接'};
let ws;
function send(m){if(ws&&ws.readyState===1)ws.send(JSON.stringify(m));}
pc.onicecandidate=e=>{if(e.candidate)send({type:'ice',payload:e.candidate.toJSON()});};
fetch('/api/remote/pair/'+code).then(r=>r.ok?r.json():Promise.reject(new Error('code'))).then(d=>{
  const wsUrl=(location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/remote/'+d.room_id+'?token='+encodeURIComponent(token);
  ws=new WebSocket(wsUrl);
  ws.onopen=async()=>{
    bar.textContent='等待被控端…';
    const offer=await pc.createOffer();await pc.setLocalDescription(offer);
    send({type:'offer',payload:offer.toJSON()});
  };
  ws.onmessage=async ev=>{const m=JSON.parse(ev.data);
    if(m.type==='answer'){await pc.setRemoteDescription({type:'answer',sdp:m.payload.sdp});}
    else if(m.type==='ice'){try{await pc.addIceCandidate(m.payload);}catch(e){}}
  };
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


@router.post("/pair")
async def create_pair(req: PairRequest, user: dict = Depends(get_current_user)):
    code = remote_service.create_pair(user["id"], req.device_id, req.room_id)
    return {"code": code}


@router.get("/pair/{code}")
async def consume_pair(code: str):
    room_id = remote_service.consume_pair(code)
    if not room_id:
        raise HTTPException(status_code=410, detail="Pair code invalid or expired")
    return {"room_id": room_id}


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

    await websocket.accept()
    await remote_service.room_join(room_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            await remote_service.room_broadcast(room_id, websocket, message)
    except WebSocketDisconnect:
        await remote_service.room_leave(room_id, websocket)
