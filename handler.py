import os, json, time, base64, uuid, subprocess, requests, websocket, runpod
COMFY_DIR = "/comfyui"
PORT = 8188
HOST = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}/ws?clientId="

def start():
    if getattr(start, "_started", False): return
    subprocess.Popen(["python","main.py","--listen","127.0.0.1","--port",str(PORT),"--disable-auto-launch"], cwd=COMFY_DIR)
    for _ in range(120):
        try:
            if requests.get(f"{HOST}/object_info", timeout=2).ok: break
        except: pass
        time.sleep(1)
    start._started = True

def queue(prompt, cid):
    r = requests.post(f"{HOST}/prompt", json={"prompt": prompt, "client_id": cid}, timeout=60); r.raise_for_status()
    return r.json()["prompt_id"]

def wait_done(pid, cid):
    ws = websocket.create_connection(WS + cid, timeout=300)
    try:
        while True:
            m = json.loads(ws.recv())
            if m.get("type")=="executing" and m["data"]["prompt_id"]==pid and m["data"]["node"] is None: return
    finally: ws.close()

def history(pid):
    r = requests.get(f"{HOST}/history/{pid}", timeout=60); r.raise_for_status()
    return r.json()[pid]

def view(fn, sub, typ):
    r = requests.get(f"{HOST}/view", params={"filename":fn,"subfolder":sub,"type":typ}, timeout=120); r.raise_for_status()
    return r.content

def load_workflow():
    with open("/comfyui/workflows/ghost_realism_workflow.json") as f: return json.load(f)

def run_flow(pos, neg):
    wf = load_workflow()
    wf["3"]["inputs"]["text"] = pos
    wf["4"]["inputs"]["text"] = neg
    wf["2"]["inputs"]["seed"] = int(time.time()*1e6)%2**32
    cid = str(uuid.uuid4())
    pid = queue(wf, cid); wait_done(pid, cid)
    out = history(pid); imgs=[]
    for node in out.get("outputs",{}).values():
        for i in node.get("images",[]):
            imgs.append(base64.b64encode(view(i["filename"], i.get("subfolder",""), i.get("type","output"))).decode())
    return imgs

def handler(event):
    start()
    data = event.get("input",{})
    pos, neg = data.get("positive",""), data.get("negative","")
    if not pos: return {"error":"positive is required"}
    return {"images_base64": run_flow(pos, neg)}

runpod.serverless.start({"handler": handler})