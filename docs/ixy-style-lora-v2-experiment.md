# ixy style LoRA v2 goal experiment

## Goal

Given a character reference, produce the redraw that the source artist would make after
applying their own proportions, facial construction, line habits, simplification,
color separation, shading, clothing-detail priorities, and pose preferences. Preserve
the referenced character identity while allowing the style adapter to change the drawing
decisions. The two Hotarugusa generated examples are evaluation targets, not training data.

## Derived dataset

- Primary: all eligible single-female images in `style_01_clean_lineart`,
  `style_02_dark_flat`, and `style_04_pastel_soft`.
- Composite auxiliary: at most 128 stratified single-female examples from
  `style_03_composite_scene`.
- Diversity auxiliary: at most 48 stratified group, male, or other-subject examples from
  the three goal clusters.
- Full-body boost: one additional training vote for primary full-body examples.
- Exclude source-duplicate rows, variant-style rows, and captions marked as comics, manga,
  four-panel comics, sketches, line art, multiple views, or text-heavy images.
- Remove source-management and quality tags. Keep visual, character, copyright, pose,
  clothing, framing, and background tags so those concepts do not collapse into the style
  trigger.
- Preserve the existing train/validation/test split. Never train on validation or test.

The first exported version contains 1,025 effective training pairs, 123 validation pairs,
and 122 test pairs. The source images and captions remain unchanged, and every copied image
is recorded with its source SHA-256.

## Frozen training foundation

- Base: `OnomaAIResearch/Illustrious-XL-v2.0`
- Base revision: `69459c1fe6f46db41ab31e6114f05acc0e06bcaa`
- Trainer: `kohya-ss/sd-scripts` v0.9.1 at
  `8f4ee8fc343b047965cd8976fca65c3a35b7593a`
- Train U-Net adapters only; base model and both text encoders remain frozen.
- Trigger: `ixy_style_v2`, always the first caption token.
- Seed: 42.

## Controlled comparison

Run two new adapters from the same initial base and the same curated dataset:

| Setting | Candidate A: linear LoRA | Candidate B: LoCon |
| --- | ---: | ---: |
| Linear rank / alpha | 16 / 8 | 16 / 8 |
| Convolution rank / alpha | none | 8 / 4 |
| U-Net learning rate | 0.00008 | 0.00006 |
| Optimizer | AdamW | AdamW |
| Scheduler / warmup | cosine / 120 steps | cosine / 120 steps |
| Total updates | 2,400 | 2,400 |
| Checkpoints | every 300 updates | every 300 updates |
| Resolution | 1024 with aspect buckets | 1024 with aspect buckets |
| Bucket range / step | 512–1536 / 64 | 512–1536 / 64 |
| Batch / accumulation | 1 / 1 | 1 / 1 |
| Min-SNR gamma | 5 | 5 |
| Network dropout | 0.05 | 0.05 |
| Weight-norm cap | 1.0 | 1.0 |

Use latent and text-encoder-output caches. Captions are static because the pinned SDXL
trainer does not allow caption shuffle or caption dropout together with text-encoder-output
caching. The cleaned captions and content diversity make static conditioning preferable for
this comparison.

Rank 8 is rejected as the main candidate because it is the capacity of the current adapter
that under-expresses the artist's local drawing decisions. Rank 32 is deferred: Candidate B
adds targeted convolution capacity for eyes, lines, folds, edges, and flat-color boundaries
with less broad memorization pressure than doubling every linear rank.

## Checkpoint selection

Evaluate steps 600, 900, 1,200, 1,500, 1,800, 2,100, and 2,400. Training loss is a health
signal, not the winner criterion. For each checkpoint, use fixed seeds and identical
reference-conditioning settings over four compositions (bust portrait, standing full body,
foreshortened action, and seated three-quarter view) and LoRA strengths 0.60, 0.75, 0.90,
and 1.05.

Select on the Pareto balance of:

1. similarity to held-out authentic artist images;
2. retention of Hotarugusa's hair, bow, flower ornaments, costume layers, bells, staff, and
   leaf silhouette;
3. artist-specific face, eye, hair, hand, body, line, color, and shading decisions;
4. prompt and composition adherence;
5. absence of copied training compositions, recurring school-uniform leakage, white-background
   lock-in, malformed hands, and identity collapse.

The winning checkpoint is copied as a new versioned artifact. The current
`ixy_style.safetensors` is never overwritten.
