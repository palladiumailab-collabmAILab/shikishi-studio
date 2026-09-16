"""Optional Gradio image-generation interface for Illustrious XL LoRAs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_image(
    base_model: str,
    lora_path: str,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    steps: int,
    guidance_scale: float,
    seed: int,
) -> Any:
    """Generate one image with a local SDXL checkpoint and LoRA file."""
    if not prompt.strip():
        raise ValueError("Prompt must not be empty.")
    model_file = Path(base_model)
    lora_file = Path(lora_path)
    if not model_file.is_file():
        raise ValueError(f"Base model file does not exist: {model_file}")
    if not lora_file.is_file():
        raise ValueError(f"LoRA file does not exist: {lora_file}")
    if width % 8 != 0 or height % 8 != 0:
        raise ValueError("Width and height must be divisible by 8.")

    try:
        import torch
        from diffusers import StableDiffusionXLPipeline
    except ImportError as error:
        raise RuntimeError(
            "The generation UI dependencies are missing. Install with: pip install '.[ui]'"
        ) from error

    pipeline = StableDiffusionXLPipeline.from_single_file(
        str(model_file), torch_dtype=torch.float16, use_safetensors=True
    )
    pipeline.enable_model_cpu_offload()
    pipeline.enable_vae_tiling()
    pipeline.enable_attention_slicing()
    pipeline.load_lora_weights(str(lora_file.parent), weight_name=lora_file.name)
    generator = torch.Generator(device="cuda").manual_seed(seed)
    result = pipeline(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
        generator=generator,
    )
    return result.images[0]


def launch_ui(host: str = "127.0.0.1", port: int = 7860) -> None:
    """Launch a browser UI without loading ML dependencies until generation."""
    try:
        import gradio as gr  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "The generation UI dependencies are missing. Install with: pip install '.[ui]'"
        ) from error

    with gr.Blocks(title="Shikishi — Illustrious XL LoRA") as interface:
        gr.Markdown("# Shikishi — Illustrious XL style LoRA generator")
        gr.Markdown("Use the same trigger word selected while preparing the training dataset.")
        with gr.Row():
            with gr.Column():
                base_model = gr.Textbox(label="Illustrious XL checkpoint (.safetensors)")
                lora_path = gr.Textbox(label="Trained LoRA (.safetensors)")
                prompt = gr.Textbox(label="Prompt", lines=4)
                negative_prompt = gr.Textbox(label="Negative prompt", lines=3)
                with gr.Row():
                    width = gr.Slider(512, 1536, value=1024, step=64, label="Width")
                    height = gr.Slider(512, 1536, value=1024, step=64, label="Height")
                with gr.Row():
                    steps = gr.Slider(1, 50, value=28, step=1, label="Steps")
                    guidance = gr.Slider(1, 12, value=5, step=0.5, label="Guidance")
                    seed = gr.Number(value=42, precision=0, label="Seed")
                generate = gr.Button("Generate", variant="primary")
            image = gr.Image(label="Generated image", type="pil")
        generate.click(
            generate_image,
            inputs=[
                base_model,
                lora_path,
                prompt,
                negative_prompt,
                width,
                height,
                steps,
                guidance,
                seed,
            ],
            outputs=image,
        )
    interface.launch(server_name=host, server_port=port, inbrowser=True)
