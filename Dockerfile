FROM runpod/worker-comfyui:5.1.0-base

RUN echo "runpod_volume:\n  base_path: /runpod-volume/models" > /comfyui/extra_model_paths.yaml

RUN cd /comfyui/custom_nodes && \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    git clone https://github.com/WASasquatch/was-node-suite-comfyui.git && \
    git clone https://github.com/bradsec/ComfyUI_StringEssentials.git

RUN cd /comfyui/custom_nodes/ComfyUI-Impact-Pack && pip install -r requirements.txt
RUN cd /comfyui/custom_nodes/was-node-suite-comfyui && pip install -r requirements.txt
RUN cd /comfyui/custom_nodes/ComfyUI_StringEssentials && if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

COPY workflows /comfyui/workflows
COPY handler.py /workspace/handler.py
WORKDIR /workspace
EXPOSE 8188
CMD ["python", "-u", "handler.py"]
