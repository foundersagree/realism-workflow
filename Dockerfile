# Production Dockerfile for RunPod Serverless ComfyUI with Realism Workflow
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# Set environment to avoid prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    python3 \
    python3-pip \
    python3-dev \
    curl \
    wget \
    ca-certificates \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Clone ComfyUI
WORKDIR /ComfyUI
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git .

# Install Python packages
RUN pip3 install --upgrade pip \
    && pip3 install -r requirements.txt \
    && pip3 uninstall -y torch torchvision torchaudio \
    && pip3 install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118 \
    && pip3 install runpod

# Install custom nodes required for the realism workflow

# 1. Impact Pack (for ImpactWildcardProcessor and ImpactConcatConditionings)
RUN git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack custom_nodes/ComfyUI-Impact-Pack \
    && cd custom_nodes/ComfyUI-Impact-Pack \
    && pip3 install impact-pack opencv-python-headless segment-anything piexif onnxruntime

# 2. String Suite (for StringPreview node)
RUN git clone https://github.com/m-sokes/ComfyUI-StringSuite custom_nodes/ComfyUI-StringSuite

# Create necessary directories
RUN mkdir -p \
    /ComfyUI/output \
    /ComfyUI/input \
    /ComfyUI/workflows \
    /ComfyUI/models/checkpoints \
    /ComfyUI/models/loras \
    /ComfyUI/models/vae \
    /ComfyUI/models/embeddings

# Copy workflow and handler files
COPY realism_workflow.json /ComfyUI/workflows/realism_workflow.json
COPY handler.py /ComfyUI/handler.py

# Set working directory
WORKDIR /ComfyUI

# Run the handler
CMD ["python3", "handler.py"]
