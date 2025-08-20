FROM runpod/worker-comfyui:5.1.0-base

RUN comfy-node-install ComfyUI-Impact-Pack

COPY workflows /comfyui/workflows
COPY handler.py /workspace/handler.py
WORKDIR /workspace
EXPOSE 8188
CMD ["python", "-u", "handler.py"]