"""Generate a small, deterministic visual QA set for the v2 style LoRAs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch
from diffusers import StableDiffusionXLPipeline

PROMPTS = [
    (
        "p01_fullbody",
        "ixy_style_v2, 1girl, solo, hotarugusa character, short light-blue bob hair, "
        "large navy bow, white and deep-blue kimono-inspired outfit, golden bell ornaments, "
        "holding a tall golden stem with three glowing leaves, full body, centered, "
        "clean white background",
    ),
    (
        "p02_portrait",
        "ixy_style_v2, 1girl, solo, hotarugusa character, short light-blue bob hair, "
        "large navy bow, white and deep-blue kimono-inspired outfit, holding a golden leaf stem, "
        "three-quarter bust portrait, large expressive blue eyes, delicate flower hair ornaments, "
        "white background",
    ),
    (
        "p03_dynamic",
        "ixy_style_v2, 1girl, solo, hotarugusa character, short light-blue bob hair, "
        "large navy bow, blue and white ceremonial outfit, golden bells, reaching one hand toward "
        "the viewer, dynamic low angle, flowing sleeves, golden leaves forming an arc above her, "
        "white background",
    ),
    (
        "p04_diagonal",
        "ixy_style_v2, 1girl, solo, hotarugusa character, short light-blue bob hair, "
        "large navy bow, white and deep-blue kimono-inspired outfit, golden bells and tassels, "
        "diagonal floating pose, elegant three-quarter view, tall golden plant framing the "
        "composition, white background",
    ),
]

NEGATIVE_PROMPT = (
    "low quality, worst quality, blurry, jpeg artifacts, bad anatomy, bad hands, "
    "extra fingers, missing fingers, extra limbs, text, watermark, logo, multiple girls"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    base_model = "MX4T/Illustrious-XL-v2.0-diffusers"
    lora_dir = Path("/qa/loras")
    output_dir = Path("/qa/out")
    output_dir.mkdir(parents=True, exist_ok=True)
    adapters = [
        ("linear", "ixy_style_v2_linear_r16_a8_s42.safetensors"),
        ("locon", "ixy_style_v2_locon_r16_a8_c8_ca4_s42.safetensors"),
    ]

    pipe = StableDiffusionXLPipeline.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        use_safetensors=True,
        local_files_only=True,
    )
    pipe.enable_model_cpu_offload()
    pipe.enable_vae_tiling()
    pipe.enable_attention_slicing()

    manifest: dict[str, object] = {
        "base_model": base_model,
        "resolution": [768, 1024],
        "steps": 20,
        "guidance_scale": 5.0,
        "negative_prompt": NEGATIVE_PROMPT,
        "seed_by_prompt": {name: 42 + index for index, (name, _) in enumerate(PROMPTS)},
        "outputs": [],
    }

    for adapter_name, filename in adapters:
        pipe.load_lora_weights(lora_dir, weight_name=filename, adapter_name=adapter_name)
        pipe.set_adapters(adapter_name, adapter_weights=1.0)
        try:
            for index, (prompt_name, prompt) in enumerate(PROMPTS):
                seed = 42 + index
                generator = torch.Generator(device="cuda").manual_seed(seed)
                image = pipe(
                    prompt=prompt,
                    negative_prompt=NEGATIVE_PROMPT,
                    width=768,
                    height=1024,
                    num_inference_steps=20,
                    guidance_scale=5.0,
                    generator=generator,
                ).images[0]
                output_path = output_dir / f"{adapter_name}_{prompt_name}.png"
                image.save(output_path)
                manifest["outputs"].append(
                    {
                        "adapter": adapter_name,
                        "lora": filename,
                        "prompt_name": prompt_name,
                        "seed": seed,
                        "path": output_path.name,
                        "bytes": output_path.stat().st_size,
                        "sha256": sha256(output_path),
                    }
                )
        finally:
            pipe.unload_lora_weights()
            torch.cuda.empty_cache()

    (output_dir / "visual_qa_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
