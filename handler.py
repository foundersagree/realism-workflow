import os, json, time, base64, uuid, subprocess, requests, websocket, runpod
COMFY_DIR = "/comfyui"
PORT = 8188
HOST = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}/ws?clientId="

def setup_models():
    print("=== DEBUG: Checking for model mounts ===")
    potential_mounts = ["/workspace/models", "/runpod-volume/models", "/network/models", "/mnt/models"]
    
    for mount in potential_mounts:
        if os.path.exists(mount):
            print(f"✅ Found: {mount}")
            try:
                contents = os.listdir(mount)
                print(f"   Contents: {contents}")
            except:
                print(f"   (Cannot list contents)")
        else:
            print(f"❌ Missing: {mount}")
    
    
    print("=== ComfyUI will use network volume directly (no copying needed) ===")

def start():
    if getattr(start, "_started", False): return
    setup_models()  # Setup models BEFORE starting ComfyUI
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

def get_available_nodes():
    try:
        r = requests.get(f"{HOST}/object_info", timeout=10)
        if r.ok:
            return r.json()
        return {}
    except:
        return {}

def get_models(model_type):
    """Return list of available model file names from both ComfyUI API and direct file system"""
    models = set()
    
    # Try ComfyUI API first
    try:
        r = requests.get(f"{HOST}/models", params={"type": model_type}, timeout=10)
        if r.ok:
            data = r.json()
            if isinstance(data, dict) and "models" in data:
                models.update(data["models"])
            elif isinstance(data, list):
                models.update(data)
    except Exception:
        pass
    
    # Also check direct file system paths where ComfyUI looks
    search_paths = [
        f"/comfyui/models/{model_type}",
        f"/runpod-volume/models/{model_type}",
        f"/workspace/models/{model_type}"
    ]
    
    for path in search_paths:
        if os.path.isdir(path):
            try:
                for file in os.listdir(path):
                    if file.endswith('.safetensors'):
                        models.add(file)
            except:
                pass
    
    return list(models)

def load_workflow():
    with open("/comfyui/workflows/realism_workflow_api.json") as f: 
        return json.load(f)

def run_flow(pos, neg, number=1, creativity=1.0):
    available_nodes = get_available_nodes()
    required_nodes = ["StringPreview", "ImpactConcatConditionings"]
    missing_nodes = [node for node in required_nodes if node not in available_nodes]
    
    if missing_nodes:
        print(f"Warning: Missing nodes: {missing_nodes}")
        print(f"Available custom nodes: {[k for k in available_nodes.keys() if not k.startswith('_')][:10]}...")
    
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
    
    wf["11"]["inputs"]["batch_size"] = max(1, min(4, int(number)))
    
    creativity_loras = ["16", "20"]  # igbaddie-XL and epiCRealismXL-KiSSEnhancer_Lora
    
    if creativity > 0.5:
        # High creativity: enable LoRAs
        pass 
    else:
        # Low creativity: bypass LoRAs
        for node_id in creativity_loras:
            if node_id in wf:
                wf[node_id]["inputs"]["strength_model"] = 0.0
                wf[node_id]["inputs"]["strength_clip"] = 0.0
    
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
    pos = data.get("positive","")
    neg = data.get("negative","")
    number = data.get("number", 1)
    creativity = data.get("creativity", 1.0)
    
    if not pos: return {"error":"positive is required"}
    
    return {"images_base64": run_flow(pos, neg, number, creativity)}

runpod.serverless.start({"handler": handler})