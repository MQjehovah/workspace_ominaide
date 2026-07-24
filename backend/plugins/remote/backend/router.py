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


VIEWER_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no'><title>OmniAide Remote</title><style>body{margin:0;background:#000;overflow:hidden;touch-action:none;font-family:sans-serif}video{width:100vw;height:100vh;object-fit:contain}#bar{position:fixed;top:8px;left:8px;color:#fff;font:13px sans-serif;background:rgba(0,0,0,.5);padding:4px 8px;border-radius:6px;z-index:10}#form{position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#1a1a2e;color:#fff;z-index:20}#form input{margin:6px;padding:10px 14px;border:none;border-radius:8px;font-size:16px;text-align:center;width:200px;outline:none}#form button{margin:8px;padding:10px 30px;border:none;border-radius:8px;background:#0078D4;color:#fff;font-size:16px;cursor:pointer}#form button:disabled{opacity:.5}#form .err{color:#ff4444;font-size:13px;margin:4px}</style></head><body>
<div id='form'><h2>远程控制</h2><input id='code' placeholder='配对码' maxlength='6' autocomplete='off'/><input id='pw' type='password' placeholder='密码（可选）' maxlength='6' autocomplete='off'/><button id='btn' onclick='connect()'>连接</button><div class='err' id='err'></div></div>
<div id='bar' style='display:none'>连接中…</div>
<video id='v' autoplay playsinline style='display:none'></video>
<script>
const v=document.getElementById('v'),bar=document.getElementById('bar'),form=document.getElementById('form'),err=document.getElementById('err');
let pc=null,dc=null,ended=false,ws=null;
function send(ev){if(dc&&dc.readyState==='open'){try{dc.send(JSON.stringify(ev))}catch(e){}}}
function btn(b){return b===2?'right':b===1?'middle':'left';}
function normAt(cx,cy){const r=v.getBoundingClientRect();const vw=v.videoWidth||r.width,vh=v.videoHeight||r.height;const sc=Math.min(r.width/vw,r.height/vh);const rw=vw*sc,rh=vh*sc;const ox=r.left+(r.width-rw)/2,oy=r.top+(r.height-rh)/2;return{x:rw>0?Math.max(0,Math.min(1,(cx-ox)/rw)):0,y:rh>0?Math.max(0,Math.min(1,(cy-oy)/rh)):0};}
v.addEventListener('mousemove',e=>{const p=normAt(e.clientX,e.clientY);send({type:'mouseMove',x:p.x,y:p.y});});
v.addEventListener('mousedown',e=>{e.preventDefault();send({type:'mouseDown',button:btn(e.button)});});
v.addEventListener('mouseup',e=>send({type:'mouseUp',button:btn(e.button)}));
v.addEventListener('wheel',e=>{e.preventDefault();send({type:'wheel',deltaY:e.deltaY});},{passive:false});
v.addEventListener('contextmenu',e=>e.preventDefault());
v.addEventListener('touchstart',e=>{e.preventDefault();const p=normAt(e.touches[0].clientX,e.touches[0].clientY);send({type:'mouseMove',x:p.x,y:p.y});send({type:'mouseDown',button:'left'});},{passive:false});
v.addEventListener('touchmove',e=>{e.preventDefault();const p=normAt(e.touches[0].clientX,e.touches[0].clientY);send({type:'mouseMove',x:p.x,y:p.y});},{passive:false});
v.addEventListener('touchend',e=>{e.preventDefault();send({type:'mouseUp',button:'left'});},{passive:false});
function ignored(c){return c==='F5'||c==='F11'||c==='F12';}
document.addEventListener('keydown',e=>{if(e.code&&!ignored(e.code)){e.preventDefault();send({type:'keyDown',code:e.code});}});
document.addEventListener('keyup',e=>{if(e.code&&!ignored(e.code)){e.preventDefault();send({type:'keyUp',code:e.code});}});
function wsSend(m){if(ws&&ws.readyState===1)ws.send(JSON.stringify(m));}
async function connect(){
  const code=document.getElementById('code').value.trim();
  const pw=document.getElementById('pw').value.trim();
  if(!code){err.textContent='请输入配对码';return}
  document.getElementById('btn').disabled=true;err.textContent='';
  const wsUrl=(location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/remote';
  ws=new WebSocket(wsUrl);
  ws.onopen=()=>{bar.textContent='验证配对码…';wsSend({type:'pair_lookup',code:code,password:pw});};
  ws.onmessage=async ev=>{const m=JSON.parse(ev.data);
    if(m.type==='pair_success'){
      form.style.display='none';bar.style.display='block';v.style.display='';
      pc=new RTCPeerConnection({iceServers:m.iceServers||[{urls:'stun:mqgeek.com:3478'},{urls:'turn:mqgeek.com:3478',username:'guest',credential:'guest'},{urls:'turn:mqgeek.com:3478?transport=tcp',username:'guest',credential:'guest'}]});
      pc.ontrack=e=>{v.srcObject=e.streams[0];bar.textContent='已连接（可控制）';setTimeout(()=>v.focus(),200);};
      pc.onicecandidate=e=>{if(e.candidate)wsSend({type:'ice',payload:e.candidate});};
      bar.textContent='等待被控端授权…';
      wsSend({type:'requestControl',name:navigator.userAgent.includes('Mobile')?'手机':'浏览器'});
    }else if(m.type==='pair_error'){
      err.textContent=m.reason||'配对失败';document.getElementById('btn').disabled=false;ws.close();
    }else if(m.type==='controlAllowed'){
      dc=pc.createDataChannel('input');pc.addTransceiver('video',{direction:'recvonly'});
      const offer=await pc.createOffer();await pc.setLocalDescription(offer);wsSend({type:'offer',payload:offer});
      bar.textContent='等待画面…';
    }else if(m.type==='controlDenied'){ended=true;bar.textContent=m.reason==='busy'?'被控端忙':'被控端拒绝';}
    else if(m.type==='revoked'){ended=true;bar.textContent='被控端断开了控制';}
    else if(m.type==='answer'){await pc.setRemoteDescription({type:'answer',sdp:m.payload.sdp});}
    else if(m.type==='ice'){try{await pc.addIceCandidate(m.payload);}catch(e){}}
  };
  ws.onclose=()=>{if(!ended&&form.style.display!=='none'){err.textContent='连接失败';document.getElementById('btn').disabled=false;}};
}
</script></body></html>"""


def _ice_servers() -> list:
    import json
    try:
        return json.loads(settings.webrtc_ice_servers)
    except Exception:
        return [{"urls": "stun:mqgeek.com:3478"}, {"urls": "turn:mqgeek.com:3478", "username": "guest", "credential": "guest"},
                {"urls": "turn:mqgeek.com:3478?transport=tcp", "username": "guest", "credential": "guest"}]


# ─── HTTP API（仅保留设备列表和 ICE 配置） ───

@router.get("/devices")
async def devices(user: dict = Depends(get_current_user)):
    return {"devices": remote_service.get_own_devices(user["id"])}


@router.get("/ice")
async def ice_config():
    return {"iceServers": _ice_servers()}


@router.get("/viewer", response_class=HTMLResponse)
async def viewer(code: str = "", password: str = ""):
    """返回独立远控页面"""
    return VIEWER_HTML


# ─── WebSocket ───

@ws_router.websocket("/ws/remote")
async def remote_websocket(websocket: WebSocket):
    """统一 WS 信令入口。消息按 type 路由：
       join{device_id, name, token} — 设备上线
       pair_request{password?} — Host 请求配对码
       pair_lookup{code, password} — Viewer 查找 Host
       requestControl / offer / answer / ice — 配对间转发
    """
    await remote_service.connect(websocket)
    device_id = None
    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "join":
                token = msg.get("token", "")
                payload = decode_access_token(token) if token else None
                user_id = int(payload.get("sub", 0)) if payload else 0
                device_id = msg.get("device_id", "")
                name = msg.get("name", "")
                await remote_service.handle_join(websocket, device_id, name, user_id)
                # 检查是否有配对请求
                pwd = msg.get("pair_password", "")
                if pwd:
                    code, pw = remote_service.create_pair(device_id, pwd)
                else:
                    code, pw = remote_service.create_pair(device_id)
                await websocket.send_json({"type": "pair_code", "code": code, "password": pw})

            elif msg_type == "pair_lookup":
                code = msg.get("code", "")
                password = msg.get("password", "")
                host_id = remote_service.verify_pair(code, password)
                if not host_id:
                    await websocket.send_json({"type": "pair_error", "reason": "配对码无效或已过期"})
                    continue
                # 绑定配对关系
                viewer_id = f"viewer_{id(websocket)}"
                remote_service.bind_pairing(code, host_id, viewer_id)
                host_ws = remote_service.get_host_ws_by_code(code)
                if host_ws:
                    await host_ws.send_json({"type": "requestControl", "name": msg.get("name", "浏览器")})
                await websocket.send_json({
                    "type": "pair_success", "host_id": host_id,
                    "iceServers": _ice_servers(),
                })

            elif msg_type in ("requestControl", "offer", "answer", "ice", "controlAllowed", "controlDenied", "revoked"):
                target_id = msg.get("target_id", "")
                if target_id:
                    # Viewer → Host: 注册 pending 并转发
                    remote_service.register_pending_viewer(target_id, websocket)
                    ok = await remote_service.forward_to_device(target_id, msg, websocket)
                elif device_id:
                    # Host → Viewer: 转发给 pending viewers
                    ok = await remote_service.forward_to_pending_viewers(device_id, msg, websocket)
                    if not ok:
                        ok = await remote_service.forward(websocket, msg)
                if not ok:
                    pass

            elif msg_type == "pair_request":
                pwd = msg.get("password", "")
                if device_id:
                    code, pw = remote_service.create_pair(device_id, pwd)
                    await websocket.send_json({"type": "pair_code", "code": code, "password": pw})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        import logging
        logging.getLogger("uvicorn").error(f"[remote] ws error: {e}")
    finally:
        await remote_service.disconnect(websocket)
