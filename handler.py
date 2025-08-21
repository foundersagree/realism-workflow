import os, json, time, base64, uuid, subprocess, requests, websocket, runpod
COMFY_DIR = "/comfyui"
PORT = 8188
HOST = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}/ws?clientId="

def start():
    if getattr(start, "_started", False): return
    # The entire try...except block for creating symbolic links has been removed.
    subprocess.Popen(["python","main.py","--listen","127.0.0.1","--port",str(PORT),"--disable-auto-launch"], cwd=COMFY_DIR)
    for _ in range(120):
        try:
            if requests.get(f"{HOST}/object_info", timeout=2).ok: break
        except: pass
        time.sleep(1)
    start._started = True

def queue(prompt, cid):
    try:
        r = requests.post(f"{HOST}/prompt", json={"prompt": prompt, "client_id": cid}, timeout=60)
        if not r.ok:
            print(f"ComfyUI Error: {r.status_code} - {r.text}")
        r.raise_for_status()
        return r.json()["prompt_id"]
    except Exception as e:
        print(f"Queue error: {e}")
        print(f"Response: {r.text if 'r' in locals() else 'No response'}")
        raise

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

def get_models(model_type):
    """Return list of available model file names for a given type, e.g. 'checkpoints', 'loras'"""
    try:
        r = requests.get(f"{HOST}/models", params={"type": model_type}, timeout=10)
        if r.ok:
            data = r.json()
            # Handle both list and dict response formats
            models = data if isinstance(data, list) else data.get("models", [])
            # The API returns a list of dicts, we need the file names
            return [model['name'] for model in models if 'name' in model]
        return []
    except Exception:
        return []

def load_workflow():
    with open("/comfyui/workflows/realism_workflow_api.json") as f: 
        return json.load(f)

def run_flow(pos, neg):
    # This pre-flight check is great for debugging!
    checkpoints = set(get_models("checkpoints"))
    loras = set(get_models("loras"))
    
    missing_models = []
    required_ckpt = "gonzalomoXLFluxPony_v40UnityXLDMD.safetensors"
    required_loras = [
        "RealSkin_xxXL_v1.safetensors",
        "add-detail-xl.safetensors",
        "igbaddie-XL.safetensors",
        "iphone_mirror_selfie_v01b.safetensors",
        "Dynamic_Lighting_by_Stable_Yogi_SDXL3_v1.safetensors",
        "epiCRealismXL-KiSSEnhancer_Lora.safetensors",
    ]

    if required_ckpt and required_ckpt not in checkpoints:
        missing_models.append(("checkpoint", required_ckpt))
    for name in required_loras:
        if name not in loras:
            missing_models.append(("lora", name))
            
    if missing_models:
        print("Missing models detected:")
        for mtype, name in missing_models:
            print(f" - {mtype}: {name}")
        raise RuntimeError(f"Missing models: {[name for _, name in missing_models]} - ensure files are present in /comfyui/models and ComfyUI indexed them")
    
    wf = load_workflow()
    
    wf["3"]["inputs"]["text"] = pos  # Positive prompt
    wf["4"]["inputs"]["text"] = neg  # Negative prompt
    wf["2"]["inputs"]["seed"] = int(time.time()*1e6)%2**32  # Random seed
    
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
