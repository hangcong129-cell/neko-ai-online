from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
import os,json,base64,hmac,time,threading
PORT=int(os.getenv("PORT","10000")); KEY=os.getenv("OPENAI_API_KEY","").strip()
USER=os.getenv("NEKO_ACCESS_USER","neko"); PASSWORD=os.getenv("NEKO_ACCESS_PASSWORD","")
MODEL=os.getenv("OPENAI_MODEL","gpt-6.1-sol")
MODELS=[x.strip() for x in os.getenv("NEKO_ALLOWED_MODELS","gpt-6.1-sol,gpt-6.1-terra,gpt-6-luna").split(",") if x.strip()]
if MODEL not in MODELS: MODELS.insert(0,MODEL)
EFFORT=os.getenv("OPENAI_REASONING_EFFORT","medium")
MAX_OUT=min(max(int(os.getenv("NEKO_MAX_OUTPUT_TOKENS","4096")),256),12000)
SYSTEM="""Bạn là NEKO AI, trợ lý riêng nói tiếng Việt tự nhiên.
Hãy trả lời đúng trọng tâm, giải thích từng bước khi cần, kiểm tra phép tính và code.
Khi viết code, đưa mã có thể chạy, nêu phụ thuộc và cách kiểm tra. Không nói đã thử nếu chưa thử.
Phân biệt điều chắc chắn và điều chưa chắc; không bịa nguồn. Không tự nhận là Claude, Gemini hay ChatGPT.
Giữ nội dung an toàn, phù hợp lứa tuổi."""
LOCK=threading.Lock(); REQUESTS={}
def dump(x): return json.dumps(x,ensure_ascii=False).encode()
def rate(ip):
 now=time.time()
 with LOCK:
  a=REQUESTS.setdefault(ip,[]); a[:]=[t for t in a if t>now-86400]
  if sum(t>now-60 for t in a)>=6 or len(a)>=30:return False
  a.append(now); return True
class H(BaseHTTPRequestHandler):
 server_version="NekoAI/1.0"
 def log_message(self,*a): print("[NEKO] "+(a[0]%a[1:]))
 def out(self,s,x,typ="application/json; charset=utf-8"):
  b=x if isinstance(x,bytes) else dump(x); self.send_response(s); self.send_header("Content-Type",typ); self.send_header("Content-Length",str(len(b))); self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("X-Frame-Options","DENY"); self.send_header("Referrer-Policy","same-origin"); self.end_headers(); self.wfile.write(b)
 def auth(self):
  if len(PASSWORD)<16:self.out(503,{"error":"Quản trị viên cần đặt NEKO_ACCESS_PASSWORD tối thiểu 16 ký tự."}); return False
  try:
   scheme,token=self.headers.get("Authorization","").split(" ",1)
   u,p=base64.b64decode(token,validate=True).decode().split(":",1)
  except Exception: u=p=""
  ok=hmac.compare_digest(u.encode(),USER.encode()) and hmac.compare_digest(p.encode(),PASSWORD.encode())
  if not ok:
   self.send_response(401); self.send_header("WWW-Authenticate",'Basic realm="NEKO AI", charset="UTF-8"'); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length","0"); self.end_headers(); return False
  return True
 def do_GET(self):
  if self.path=="/healthz":self.out(200,{"ok":True,"service":"neko-ai"}); return
  if not self.auth():return
  if self.path in ("/","/index.html"):
   from pathlib import Path
   try:self.out(200,(Path(__file__).parent/"index.html").read_bytes(),"text/html; charset=utf-8")
   except OSError:self.out(500,{"error":"Không tìm thấy index.html"})
  elif self.path=="/api/config":self.out(200,{"model":MODEL,"models":MODELS,"configured":bool(KEY)})
  elif self.path=="/api/health":self.out(200 if KEY else 503,{"connected":bool(KEY),"message":"AI đã kết nối" if KEY else "Quản trị viên chưa cấu hình API key."})
  else:self.out(404,{"error":"Không tìm thấy trang."})
 def do_POST(self):
  if not self.auth():return
  origin=self.headers.get("Origin")
  if origin and origin.split("://",1)[-1].lower()!=self.headers.get("Host","").lower():self.out(403,{"error":"Nguồn yêu cầu không hợp lệ."}); return
  if self.path!="/api/chat":self.out(404,{"error":"Không tìm thấy API."}); return
  if not KEY:self.out(503,{"error":"Quản trị viên chưa cấu hình OPENAI_API_KEY trong Render."}); return
  if not rate(self.client_address[0]):self.out(429,{"error":"Đã chạm giới hạn tạm thời. Hãy thử lại sau."}); return
  try:
   n=int(self.headers.get("Content-Length","0"))
   if not 1<=n<=1500000:raise ValueError("Tin nhắn không hợp lệ hoặc quá lớn.")
   data=json.loads(self.rfile.read(n)); model=str(data.get("model",MODEL))
   if model not in MODELS:raise ValueError("Model chưa được cho phép.")
   msgs=[]
   for m in data.get("messages",[])[-30:]:
    if isinstance(m,dict) and m.get("role") in ("user","assistant") and str(m.get("content","")).strip():msgs.append({"role":m["role"],"content":str(m["content"])[:20000]})
   if not msgs or not any(m["role"]=="user" for m in msgs):raise ValueError("Chưa có tin nhắn.")
   self.stream(model,msgs)
  except (ValueError,json.JSONDecodeError,UnicodeDecodeError) as e:self.out(400,{"error":str(e)})
  except (BrokenPipeError,ConnectionResetError):return
  except Exception as e:
   try:self.out(500,{"error":"Lỗi NEKO: "+str(e)[:300]})
   except Exception:pass
 def stream(self,model,msgs):
  data={"model":model,"instructions":SYSTEM,"input":msgs,"reasoning":{"effort":EFFORT},"max_output_tokens":MAX_OUT,"stream":True,"store":False}
  req=Request("https://api.openai.com/v1/responses",data=dump(data),headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json","Accept":"text/event-stream"})
  try:r=urlopen(req,timeout=300)
  except HTTPError as e:
   detail=e.read().decode("utf-8","replace")[:2000]
   try:detail=json.loads(detail).get("error",{}).get("message",detail)
   except Exception:pass
   self.out(e.code,{"error":"OpenAI API: "+str(detail)[:1600]}); return
  except URLError:self.out(503,{"error":"Máy chủ không kết nối được OpenAI API."}); return
  self.send_response(200); self.send_header("Content-Type","application/x-ndjson; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("X-Accel-Buffering","no"); self.end_headers()
  try:
   with r:
    for raw in r:
     line=raw.decode("utf-8","replace").strip()
     if not line.startswith("data:"):continue
     try:event=json.loads(line[5:].strip())
     except json.JSONDecodeError:continue
     if event.get("type")=="response.output_text.delta":self.wfile.write(dump({"text":event.get("delta","")})+b"\n"); self.wfile.flush()
     elif event.get("type") in ("response.failed","error"):
      err=event.get("error") or event.get("response",{}).get("error") or {}; self.wfile.write(dump({"error":err.get("message","OpenAI API gặp lỗi.") if isinstance(err,dict) else str(err)})+b"\n"); self.wfile.flush()
  except (BrokenPipeError,ConnectionResetError):pass
def main():
 if len(PASSWORD)<16:raise SystemExit("Hãy đặt NEKO_ACCESS_PASSWORD tối thiểu 16 ký tự.")
 if not KEY:print("[NEKO] Chưa có OPENAI_API_KEY; website chạy nhưng chat chưa bật.")
 print("NEKO listening on",PORT); ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
if __name__=="__main__":main()
