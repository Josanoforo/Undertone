"""Direct loopback HTTP and Windows TCP ownership observations; no credentials."""
import ctypes, datetime, http.client, json, os, socket, struct, sys, time
from ctypes import wintypes

class Row(ctypes.Structure):
    _fields_=[("state",wintypes.DWORD),("local",wintypes.DWORD),("lport",wintypes.DWORD),("remote",wintypes.DWORD),("rport",wintypes.DWORD),("pid",wintypes.DWORD)]

def tcp_rows(port):
    api=ctypes.windll.iphlpapi.GetExtendedTcpTable; size=wintypes.ULONG()
    if api(None,ctypes.byref(size),True,2,5,0)!=122:raise OSError("TCP table unavailable")
    buf=ctypes.create_string_buffer(size.value)
    if api(buf,ctypes.byref(size),True,2,5,0):raise OSError("TCP table unavailable")
    count=ctypes.cast(buf,ctypes.POINTER(wintypes.DWORD)).contents.value
    start=ctypes.addressof(buf)+ctypes.sizeof(wintypes.DWORD);result=[]
    for i in range(count):
        row=Row.from_address(start+i*ctypes.sizeof(Row))
        lp=socket.ntohs(row.lport&65535);rp=socket.ntohs(row.rport&65535)
        if lp==port or rp==port:
            result.append({"state":row.state,"local":socket.inet_ntoa(struct.pack("<I",row.local)),"port":lp,"remote":socket.inet_ntoa(struct.pack("<I",row.remote)),"remotePort":rp,"pid":row.pid})
    return result

def classify(rows,port,client_port,server_pid,client_pid):
    endpoint=[r for r in rows if r["port"]==port and r["remotePort"]==0 and r["local"] in ("127.0.0.1","0.0.0.0") and r["state"] in (0,2)]
    if any(r["pid"]!=server_pid for r in endpoint) or len(endpoint)>1:return False,"conflicting_listener"
    owner=[r for r in rows if r["state"]==5 and r["local"]=="127.0.0.1" and r["port"]==port and r["remote"]=="127.0.0.1" and r["remotePort"]==client_port]
    client=[r for r in rows if r["local"]=="127.0.0.1" and r["port"]==client_port and r["remote"]=="127.0.0.1" and r["remotePort"]==port]
    if len(owner)>1 or any(r["pid"]!=server_pid for r in owner) or len(client)>1 or any(r["pid"]!=client_pid for r in client):return False,"conflicting_connection"
    if len(owner)==1 and len(client)==1:return True,"established_tuple"
    return False,"ownership_unavailable"

def probe_one(path,port,pid,table_fn=tcp_rows,connect=socket.create_connection,client_pid=None,sleep=time.sleep):
    result={"path":path,"httpOk":False,"ownershipVerified":False,"ownershipMethod":None,"ownershipStatus":"not_observed","listenerStates":[]}
    body=b"";client_pid=os.getpid() if client_pid is None else client_pid
    try:
        with connect(("127.0.0.1",port),timeout=3) as conn:
            conn.settimeout(5);local=conn.getsockname();peer=conn.getpeername()
            if local[0]!="127.0.0.1" or peer!=("127.0.0.1",port):raise OSError("loopback tuple mismatch")
            status="ownership_unavailable";rows=[]
            for attempt in range(6):
                try:
                    rows=table_fn(port);ok,status=classify(rows,port,local[1],pid,client_pid)
                except Exception:ok=False;status="ownership_unavailable"
                if ok or status.startswith("conflicting_"):break
                if attempt<5:sleep(0.05)
            result["ownershipVerified"]=ok;result["ownershipMethod"]="windows_tcp_established_tuple" if ok else None;result["ownershipStatus"]=status
            result["listenerStates"]=[{"state":r["state"],"pid":r["pid"]} for r in rows if r["port"]==port and r["remotePort"]==0 and r["state"] in (0,2)]
            result["localPort"]=local[1]
            conn.sendall(("GET "+path+" HTTP/1.0\r\nHost: 127.0.0.1:"+str(port)+"\r\nConnection: close\r\n\r\n").encode("ascii"))
            response=http.client.HTTPResponse(conn);response.begin();result["httpOk"]=response.status==200
            body=response.read(262145)
            if len(body)>262144:raise OSError("response too large")
    except Exception:
        result["httpOk"]=False
        result["transportError"]="loopback_request_failed"
    return result,body

def observe(port,pid,provider,table_fn=tcp_rows,connect=socket.create_connection,client_pid=None,sleep=time.sleep):
    root,_=probe_one("/",port,pid,table_fn,connect,client_pid,sleep)
    health,body=probe_one("/api/health",port,pid,table_fn,connect,client_pid,sleep)
    clean=None
    try:
        data=json.loads(body.decode("utf8"));ai=next(x for x in data["providers"] if x.get("name")==provider)
        asr=next((x for x in data["providers"] if x.get("name")=="faster-whisper-local"),{})
        clean={"ok":data.get("ok"),"version":data.get("version"),"provider":{k:ai.get(k) for k in ("name","model","configured","available","tested")},"asr":{k:asr.get(k) for k in ("name","configured","available","tested")}}
    except (ValueError,KeyError,TypeError,StopIteration):pass
    return {"observedAtUtc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"httpReady":root["httpOk"],"healthOk":bool(health["httpOk"] and clean and clean["ok"] is True),"ownershipVerified":bool(root["ownershipVerified"] and health["ownershipVerified"]),"ownershipMethod":"windows_tcp_established_tuple" if root["ownershipVerified"] and health["ownershipVerified"] else None,"root":root,"healthRequest":health,"health":clean}

if __name__=="__main__":
    if len(sys.argv)!=4 or not sys.argv[1].isdigit() or not sys.argv[2].isdigit() or sys.argv[3] not in ("claude","ollama"):raise SystemExit("invalid probe arguments")
    port,pid=int(sys.argv[1]),int(sys.argv[2])
    if not 1<=port<=65535 or pid<=0:raise SystemExit("invalid probe target")
    print(json.dumps(observe(port,pid,sys.argv[3]),ensure_ascii=True,separators=(",",":")))
