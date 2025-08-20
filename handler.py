import runpod
import json
import uuid
import os
import sys
import base64
import random
from typing import Dict, List, Any

# Add ComfyUI to path
sys.path.append('/ComfyUI')

# Import ComfyUI components
import execution
import folder_paths
import server

# Initialize ComfyUI
def init_comfyui():
    """Initialize ComfyUI server and nodes"""
    # Load all custom nodes
    folder_paths.init_custom_nodes()
    
    # Initialize server
    server_instance = server.PromptServer(None)
    return server_instance

# Global server instance
comfy_server = None

def find_node_by_title(workflow: Dict[str, Any], title: str) -> str | None:
    """Finds the first node ID in the workflow with a matching title."""
    for node_id, node_data in workflow.items():
        if node_data.get("_meta", {}).get("title") == title:
            return node_id
    return None

def handler(job: Dict[str, Any]):
    """
    RunPod serverless handler for realism workflow
    """
    global comfy_server
    
    try:
        # Initialize ComfyUI on the first run (cold start)
        if comfy_server is None:
            print("Initializing ComfyUI...")
            comfy_server = init_comfyui()
            
            # Configure model paths for RunPod network volume
            if os.path.exists("/runpod-volume"):
                print("Configuring RunPod network volume paths...")
                
                model_paths = [
                    ("/runpod-volume/models/checkpoints", "checkpoints"),
                    ("/runpod-volume/models/loras", "loras"),
                    ("/runpod-volume/models/vae", "vae"),
                    ("/runpod-volume/models/embeddings", "embeddings")
                ]
                
                for path, folder_type in model_paths:
                    if os.path.exists(path):
                        if folder_type in folder_paths.folder_names_and_paths:
                            if path not in folder_paths.folder_names_and_paths[folder_type][0]:
                                folder_paths.folder_names_and_paths[folder_type][0].append(path)
                                print(f"Added {folder_type} path: {path}")
        
        # Get input parameters
        job_input = job.get('input', {})
        
        # Load the API-formatted workflow
        workflow_path = '/ComfyUI/workflows/realism_workflow_api.json'
        with open(workflow_path, 'r') as f:
            workflow = json.load(f)
        
        # Update parameters using titles for robustness
        
        # Update positive prompt
        pos_prompt_node_id = find_node_by_title(workflow, "Positive Prompt")
        if pos_prompt_node_id and 'prompt' in job_input:
            workflow[pos_prompt_node_id]['inputs']['text'] = job_input['prompt']

        # Update negative prompt
        neg_prompt_node_id = find_node_by_title(workflow, "Negative Prompt")
        if neg_prompt_node_id:
            negative = job_input.get('negative_prompt', 
                "bad hands, extra fingers, missing limbs, blurry, lowres, cartoon, anime, fantasy, gothic, emo, glitch, overexposed, deformed, cropped, watermark, sci-fi, non-human, unrealistic skin, poor anatomy, tattoos, piercings")
            workflow[neg_prompt_node_id]['inputs']['text'] = negative

        # Update KSampler seed
        ksampler_node_id = find_node_by_title(workflow, "KSampler")
        if ksampler_node_id:
            if 'seed' in job_input:
                workflow[ksampler_node_id]['inputs']['seed'] = job_input['seed']
            else:
                workflow[ksampler_node_id]['inputs']['seed'] = random.randint(0, 2**32 - 1)

        # Update image dimensions
        latent_image_node_id = find_node_by_title(workflow, "Empty Latent Image")
        if latent_image_node_id:
            workflow[latent_image_node_id]['inputs']['width'] = job_input.get('width', 1024)
            workflow[latent_image_node_id]['inputs']['height'] = job_input.get('height', 1536)
            workflow[latent_image_node_id]['inputs']['batch_size'] = min(job_input.get('batch_size', 1), 4)
        
        # Generate unique prompt ID
        prompt_id = str(uuid.uuid4())
        print(f"Processing request with prompt_id: {prompt_id}")
        
        # Validate the workflow
        validation_result = execution.validate_prompt(workflow)
        if validation_result[0] is False:
            return {
                "error": f"Invalid workflow: {validation_result[1]}",
                "status": "failed"
            }
        
        # Execute the workflow
        print("Executing workflow...")
        outputs = {}
        prompt_executor = execution.PromptExecutor(comfy_server)
        
        executed_outputs = prompt_executor.execute(
            workflow,
            prompt_id,
            {"client_id": prompt_id},
            outputs
        )
        
        # Collect results
        results = []
        output_dir = "/ComfyUI/output"
        
        for node_id, node_output in executed_outputs.items():
            if 'images' in node_output:
                for i, image_data in enumerate(node_output['images']):
                    if 'filename' in image_data:
                        image_path = os.path.join(output_dir, image_data['filename'])
                        
                        if os.path.exists(image_path):
                            with open(image_path, 'rb') as f:
                                image_base64 = base64.b64encode(f.read()).decode('utf-8')
                                results.append({
                                    "image_base64": image_base64,
                                    "filename": image_data['filename']
                                })
                                print(f"Image {i+1} generated: {image_data['filename']}")
                            
                            try:
                                os.remove(image_path)
                            except:
                                pass
        
        print(f"Successfully generated {len(results)} images")
        
        return {
            "status": "success",
            "images": results
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in handler: {error_trace}")
        return {
            "status": "error",
            "error": str(e),
            "traceback": error_trace
        }

# RunPod serverless entrypoint
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
