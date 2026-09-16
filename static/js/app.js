import {NetworkError, api} from './api.js?v=20260825-quality1';
import {
  createImageCard,
  createLoadingMessage,
  createResultMessage,
  createUserMessage,
} from './ui.js?v=20260825-multiref5';

const JOB_POLL_INTERVAL_MS = 1500;
const MAX_JOB_POLL_FAILURES = 120;
const BASE_NEGATIVE_PROMPT = 'lowres, blurry, bad anatomy, text, watermark';
const QUALITY_PRESETS = {
  draft: {size: '512x512', steps: 16},
  standard: {size: '1024x1024', steps: 30},
  high: {size: '1024x1024', steps: 40},
};
const characterProfiles = new Map();
const characterReferences = [];
let poseReference = null;

const elements = {
  form: document.querySelector('#generator'),
  prompt: document.querySelector('#prompt'),
  conversation: document.querySelector('#conversation'),
  submit: document.querySelector('#submit'),
  status: document.querySelector('#status'),
  activeModel: document.querySelector('#active-model'),
  lora: document.querySelector('#lora'),
  loraValue: document.querySelector('#lora-value'),
  advanced: document.querySelector('#advanced'),
  composerWrap: document.querySelector('.composer-wrap'),
  qualityPreset: document.querySelector('#quality-preset'),
  qualityAdvice: document.querySelector('#quality-advice'),
  size: document.querySelector('#size'),
  steps: document.querySelector('#steps'),
  history: document.querySelector('#history'),
  userTemplate: document.querySelector('#user-template'),
  imageTemplate: document.querySelector('#image-template'),
  model: document.querySelector('#model'),
  modelDetail: document.querySelector('#model-detail'),
  jobStatus: document.querySelector('#job-status'),
  singleSubject: document.querySelector('#single-subject'),
  standardProportions: document.querySelector('#standard-proportions'),
  characterPreset: document.querySelector('#character-preset'),
  useTriggerWords: document.querySelector('#use-trigger-words'),
  characterReferenceFiles: document.querySelector('#character-reference-files'),
  characterReferenceStatus: document.querySelector('#character-reference-status'),
  characterReferenceList: document.querySelector('#character-reference-list'),
  referenceIpScale: document.querySelector('#reference-ip-scale'),
  referenceIpScaleValue: document.querySelector('#reference-ip-scale-value'),
  referenceFaceIpScale: document.querySelector('#reference-face-ip-scale'),
  referenceFaceIpScaleValue: document.querySelector('#reference-face-ip-scale-value'),
  referenceFaceRefinementStrength: document.querySelector('#reference-face-refinement-strength'),
  referenceFaceRefinementStrengthValue: document.querySelector('#reference-face-refinement-strength-value'),
  posePrompt: document.querySelector('#pose-prompt'),
  poseReferenceFile: document.querySelector('#pose-reference-file'),
  poseReferenceClear: document.querySelector('#pose-reference-clear'),
  poseReferenceStatus: document.querySelector('#pose-reference-status'),
  poseReferencePreviewWrap: document.querySelector('#pose-reference-preview-wrap'),
  poseReferencePreview: document.querySelector('#pose-reference-preview'),
  poseReferenceStrength: document.querySelector('#pose-reference-strength'),
  poseReferenceStrengthValue: document.querySelector('#pose-reference-strength-value'),
  poseReferenceZoom: document.querySelector('#pose-reference-zoom'),
  poseReferenceZoomValue: document.querySelector('#pose-reference-zoom-value'),
  poseReferenceFocusX: document.querySelector('#pose-reference-focus-x'),
  poseReferenceFocusY: document.querySelector('#pose-reference-focus-y'),
};

function buildGeneratePayload(prompt) {
  const [width, height] = document.querySelector('#size').value.split('x').map(Number);
  const seed = document.querySelector('#seed').value;
  const payload = {
    prompt,
    width,
    height,
    lora_scale: Number(elements.lora.value),
    negative_prompt: document.querySelector('#negative').value,
    steps: Number(document.querySelector('#steps').value),
    guidance_scale: Number(document.querySelector('#cfg').value),
    seed: seed ? Number(seed) : null,
    num_images: Number(document.querySelector('#count').value),
    model_id: elements.model.value,
    single_subject: elements.singleSubject.checked,
    standard_proportions: elements.standardProportions.checked,
    use_trigger_words: elements.useTriggerWords.checked,
    character_profile_id: elements.characterPreset.value || null,
    pose_prompt: elements.posePrompt.value.trim(),
  };
  if (characterReferences.length) {
    payload.character_references = characterReferences.map((reference) => ({
      reference_image_id: reference.id,
      role: reference.role,
      focus_x: reference.focusX,
      focus_y: reference.focusY,
      zoom: reference.zoom,
    }));
    payload.reference_ip_adapter_scale = Number(elements.referenceIpScale.value);
    payload.reference_face_ip_adapter_scale = Number(elements.referenceFaceIpScale.value);
    payload.reference_face_refinement_strength = Number(elements.referenceFaceRefinementStrength.value);
  }
  if (poseReference) {
    payload.pose_reference_image_id = poseReference.id;
    payload.pose_reference_strength = Number(elements.poseReferenceStrength.value);
    payload.pose_reference_zoom = Number(elements.poseReferenceZoom.value);
    payload.pose_reference_focus_x = Number(elements.poseReferenceFocusX.value);
    payload.pose_reference_focus_y = Number(elements.poseReferenceFocusY.value);
  }
  return payload;
}

function updateQualityAdvice() {
  const effectivePoseSteps = poseReference
    ? Number(elements.steps.value) * Number(elements.poseReferenceStrength.value)
    : null;
  if (effectivePoseSteps !== null && effectivePoseSteps < 6) {
    elements.qualityAdvice.hidden = false;
    elements.qualityAdvice.textContent =
      `注意：ポーズ画像の実効stepsは約${effectivePoseSteps.toFixed(1)}です。` +
      '輪郭破綻を避けるには「標準」以上を推奨します。';
    return;
  }
  if (elements.qualityPreset.value === 'draft') {
    elements.qualityAdvice.hidden = false;
    elements.qualityAdvice.textContent =
      'ドラフトは構図確認用です。顔・衣装・通常等身の確定には「標準」以上を使用してください。';
    return;
  }
  elements.qualityAdvice.hidden = true;
  elements.qualityAdvice.textContent = '';
}

function applyQualityPreset() {
  const preset = QUALITY_PRESETS[elements.qualityPreset.value];
  if (preset) {
    elements.size.value = preset.size;
    elements.steps.value = preset.steps;
  }
  updateQualityAdvice();
}

function syncQualityPreset() {
  const match = Object.entries(QUALITY_PRESETS).find(
    ([, preset]) => preset.size === elements.size.value && preset.steps === Number(elements.steps.value),
  );
  elements.qualityPreset.value = match?.[0] || 'custom';
  updateQualityAdvice();
}

function setAdvanced(open) {
  elements.advanced.hidden = !open;
  elements.composerWrap.classList.toggle('expanded', open);
}

function updateReferenceScaleLabels() {
  elements.referenceIpScaleValue.textContent = Number(elements.referenceIpScale.value).toFixed(2);
  elements.referenceFaceIpScaleValue.textContent = Number(elements.referenceFaceIpScale.value).toFixed(2);
  elements.referenceFaceRefinementStrengthValue.textContent = Number(elements.referenceFaceRefinementStrength.value).toFixed(2);
}

function updateCardPreview(reference, image) {
  const focusX = reference.focusX * 100;
  const focusY = reference.focusY * 100;
  image.style.objectPosition = `${focusX}% ${focusY}%`;
  image.style.transform = `scale(${reference.zoom})`;
  image.style.transformOrigin = `${focusX}% ${focusY}%`;
}

function addReferenceRange(controls, reference, image, labelText, key, min, max, step) {
  const label = document.createElement('label');
  label.append(document.createTextNode(labelText));
  const input = document.createElement('input');
  input.type = 'range';
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(reference[key]);
  const output = document.createElement('output');
  output.textContent = key === 'zoom' ? `${reference[key].toFixed(1)}×` : reference[key].toFixed(2);
  input.addEventListener('input', () => {
    reference[key] = Number(input.value);
    output.textContent = key === 'zoom' ? `${reference[key].toFixed(1)}×` : reference[key].toFixed(2);
    updateCardPreview(reference, image);
  });
  label.append(input, output);
  controls.append(label);
}

function renderCharacterReferences() {
  elements.characterReferenceList.replaceChildren();
  characterReferences.forEach((reference, index) => {
    const card = document.createElement('article');
    card.className = 'reference-card';
    const preview = document.createElement('div');
    preview.className = 'reference-card-preview';
    const image = document.createElement('img');
    image.src = `${reference.preview_url}?v=${reference.source_sha256}`;
    image.alt = `キャラクター参照 ${index + 1}`;
    preview.append(image);
    updateCardPreview(reference, image);

    const controls = document.createElement('div');
    controls.className = 'reference-card-controls';
    const roleLabel = document.createElement('label');
    roleLabel.append(document.createTextNode('役割'));
    const role = document.createElement('select');
    role.add(new Option('全体・衣装・髪', 'appearance'));
    role.add(new Option('顔', 'face'));
    role.value = reference.role;
    role.addEventListener('change', () => {
      reference.role = role.value;
      if (reference.role === 'face' && reference.zoom === 1) {
        reference.zoom = 2;
        reference.focusY = 0.35;
        renderCharacterReferences();
      }
    });
    roleLabel.append(role);
    controls.append(roleLabel);
    addReferenceRange(controls, reference, image, '拡大', 'zoom', 1, 4, 0.1);
    addReferenceRange(controls, reference, image, '中心・左右', 'focusX', 0, 1, 0.01);
    addReferenceRange(controls, reference, image, '中心・上下', 'focusY', 0, 1, 0.01);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'reference-remove';
    remove.textContent = 'この参照を解除';
    remove.addEventListener('click', () => {
      characterReferences.splice(index, 1);
      renderCharacterReferences();
      elements.characterReferenceStatus.textContent = `${characterReferences.length}/6枚を使用します`;
    });
    controls.append(remove);
    card.append(preview, controls);
    elements.characterReferenceList.append(card);
  });
}

async function uploadCharacterReferences() {
  const available = 6 - characterReferences.length;
  const files = Array.from(elements.characterReferenceFiles.files).slice(0, available);
  if (!files.length) return;
  elements.characterReferenceFiles.disabled = true;
  elements.characterReferenceStatus.classList.remove('error');
  try {
    for (const [index, file] of files.entries()) {
      elements.characterReferenceStatus.textContent = `参照画像を確認中… (${index + 1}/${files.length})`;
      const uploaded = await api.uploadReferenceImage(file);
      characterReferences.push({...uploaded, role: 'appearance', focusX: 0.5, focusY: 0.5, zoom: 1});
    }
    renderCharacterReferences();
    elements.characterReferenceStatus.textContent = `${characterReferences.length}/6枚を使用します`;
  } catch (error) {
    elements.characterReferenceStatus.classList.add('error');
    elements.characterReferenceStatus.textContent = `エラー: ${error.message}`;
  } finally {
    elements.characterReferenceFiles.disabled = false;
    elements.characterReferenceFiles.value = '';
  }
}

function updatePoseReferencePreview() {
  const zoom = Number(elements.poseReferenceZoom.value);
  const focusX = Number(elements.poseReferenceFocusX.value) * 100;
  const focusY = Number(elements.poseReferenceFocusY.value) * 100;
  elements.poseReferencePreview.style.objectPosition = `${focusX}% ${focusY}%`;
  elements.poseReferencePreview.style.transform = `scale(${zoom})`;
  elements.poseReferencePreview.style.transformOrigin = `${focusX}% ${focusY}%`;
  elements.poseReferenceStrengthValue.textContent = Number(elements.poseReferenceStrength.value).toFixed(2);
  elements.poseReferenceZoomValue.textContent = `${zoom.toFixed(1)}×`;
}

function clearPoseReference() {
  poseReference = null;
  elements.poseReferenceFile.value = '';
  elements.poseReferencePreview.removeAttribute('src');
  elements.poseReferencePreviewWrap.hidden = true;
  elements.poseReferenceClear.hidden = true;
  elements.poseReferenceStatus.classList.remove('error');
  elements.poseReferenceStatus.textContent = '人物の位置や姿勢をimg2imgで誘導します。';
  updateQualityAdvice();
}

async function uploadPoseReference() {
  const file = elements.poseReferenceFile.files[0];
  if (!file) return;
  elements.poseReferenceFile.disabled = true;
  elements.poseReferenceStatus.classList.remove('error');
  elements.poseReferenceStatus.textContent = 'ポーズ画像を確認中…';
  try {
    poseReference = await api.uploadReferenceImage(file);
    elements.poseReferencePreview.src = `${poseReference.preview_url}?v=${poseReference.source_sha256}`;
    elements.poseReferencePreviewWrap.hidden = false;
    elements.poseReferenceClear.hidden = false;
    elements.poseReferenceStatus.textContent = `${poseReference.width}×${poseReference.height} を使用します`;
    updatePoseReferencePreview();
    updateQualityAdvice();
  } catch (error) {
    clearPoseReference();
    elements.poseReferenceStatus.classList.add('error');
    elements.poseReferenceStatus.textContent = `エラー: ${error.message}`;
  } finally {
    elements.poseReferenceFile.disabled = false;
  }
}

async function saveEvaluation(button) {
  const panel = button.closest('.evaluation');
  button.disabled = true;
  const status = panel.querySelector('[data-evaluation-status]');
  status.textContent = '保存中…';
  try {
    await api.saveEvaluation(button.dataset.saveEvaluation, {
      identity_score: Number(panel.querySelector('[data-score="identity"]').value),
      style_score: Number(panel.querySelector('[data-score="style"]').value),
      pose_score: Number(panel.querySelector('[data-score="pose"]').value),
      notes: panel.querySelector('[data-evaluation-notes]').value,
    });
    status.textContent = '保存しました';
  } catch (error) {
    status.textContent = `エラー: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

async function addHistoryImageAsReference(button) {
  if (characterReferences.length >= 6) {
    elements.characterReferenceStatus.classList.add('error');
    elements.characterReferenceStatus.textContent = 'キャラクター参照は最大6枚です。';
    setAdvanced(true);
    return;
  }
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = '追加中…';
  try {
    const uploaded = await api.createReferenceFromHistory(button.dataset.useAsReference);
    characterReferences.push({...uploaded, role: 'appearance', focusX: 0.5, focusY: 0.5, zoom: 1});
    renderCharacterReferences();
    setAdvanced(true);
    elements.characterReferenceStatus.classList.remove('error');
    elements.characterReferenceStatus.textContent = `${characterReferences.length}/6枚を使用します`;
    elements.characterReferenceList.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    button.textContent = '追加済み';
  } catch (error) {
    button.textContent = originalText;
    elements.characterReferenceStatus.classList.add('error');
    elements.characterReferenceStatus.textContent = `エラー: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

function setGenerating(isGenerating) {
  elements.submit.disabled = isGenerating;
  elements.submit.innerHTML = isGenerating ? '生成中…' : '生成する <span>↑</span>';
}

function updateJobStatus(job) {
  elements.jobStatus.hidden = false;
  elements.jobStatus.textContent = `${job.message || job.status} (${Math.round(job.progress * 100)}%)`;
}

async function refreshStatus() {
  const status = await api.getStatus();
  elements.status.textContent = status.ready
    ? `準備完了 · ${status.device.toUpperCase()}`
    : `LoRA待機中 · ${status.device.toUpperCase()}`;
}

async function refreshHistory() {
  const history = await api.getHistory();
  elements.history.replaceChildren();
  if (!history.length) {
    elements.history.textContent = 'まだ生成履歴はありません。';
    return;
  }
  history.forEach((item) => {
    const card = createImageCard(item, addHistoryImageAsReference, saveEvaluation);
    card.title = item.prompt;
    elements.history.append(card);
  });
}

async function loadModels() {
  const models = await api.getModels();
  elements.model.replaceChildren();
  models.forEach((model) => {
    const option = new Option(model.name, model.id);
    option.dataset.detail = `${model.lora_filename} · 推奨強度 ${model.default_lora_scale}`;
    elements.model.add(option);
  });
  const syncModelDetails = () => {
    const selectedModel = elements.model.selectedOptions[0];
    elements.modelDetail.textContent = selectedModel?.dataset.detail || '';
    elements.activeModel.textContent = selectedModel?.textContent || 'モデル未選択';
  };
  elements.model.addEventListener('change', syncModelDetails);
  syncModelDetails();
}

async function loadCharacterProfiles() {
  const profiles = await api.getCharacterProfiles();
  characterProfiles.clear();
  elements.characterPreset.replaceChildren(new Option('なし（自由入力）', ''));
  profiles.forEach((profile) => {
    characterProfiles.set(profile.id, profile);
    elements.characterPreset.add(new Option(profile.name, profile.id));
  });
}

async function waitForJob(jobId) {
  let failures = 0;
  let job;
  while (true) {
    try {
      job = await api.getJob(jobId);
      failures = 0;
    } catch (error) {
      if (!(error instanceof NetworkError) || failures >= MAX_JOB_POLL_FAILURES) throw error;
      failures += 1;
      elements.jobStatus.hidden = false;
      elements.jobStatus.textContent = `通信を再接続中… (${failures}/${MAX_JOB_POLL_FAILURES})`;
      await new Promise((resolve) => setTimeout(resolve, Math.min(1000 * failures, 5000)));
      continue;
    }
    updateJobStatus(job);
    if (job.status !== 'queued' && job.status !== 'running') break;
    await new Promise((resolve) => setTimeout(resolve, JOB_POLL_INTERVAL_MS));
  }
  if (job.status !== 'completed') throw new Error(job.error || job.message || '生成に失敗しました');
  return job;
}

async function handleGeneration(event) {
  event.preventDefault();
  const prompt = elements.prompt.value.trim();
  if (!prompt) return;

  elements.conversation.append(createUserMessage(elements.userTemplate, prompt));
  elements.prompt.value = '';
  setGenerating(true);
  const loading = createLoadingMessage();
  elements.conversation.append(loading);
  loading.scrollIntoView({behavior: 'smooth', block: 'end'});

  try {
    const job = await api.createJob(buildGeneratePayload(prompt));
    updateJobStatus(job);
    const completedJob = await waitForJob(job.id);
    const result = createResultMessage(
      elements.imageTemplate,
      completedJob.images,
      addHistoryImageAsReference,
      saveEvaluation,
    );
    elements.conversation.replaceChild(result.fragment, loading);
    result.grid.scrollIntoView({behavior: 'smooth', block: 'end'});
    try {
      await refreshHistory();
    } catch (error) {
      if (!(error instanceof NetworkError)) throw error;
    }
  } catch (error) {
    loading.querySelector('p').textContent = `エラー: ${error.message}`;
  } finally {
    setGenerating(false);
    elements.jobStatus.hidden = true;
  }
}

function bindEvents() {
  elements.lora.addEventListener('input', () => {
    elements.loraValue.textContent = Number(elements.lora.value).toFixed(2);
  });
  document.querySelector('#new-chat').addEventListener('click', () => {
    elements.conversation.replaceChildren(document.querySelector('.assistant-message').cloneNode(true));
    elements.prompt.focus();
  });
  document.querySelector('#advanced-toggle').addEventListener('click', () => {
    setAdvanced(elements.advanced.hidden);
  });
  elements.qualityPreset.addEventListener('change', applyQualityPreset);
  elements.size.addEventListener('change', syncQualityPreset);
  elements.steps.addEventListener('input', syncQualityPreset);
  elements.characterPreset.addEventListener('change', () => {
    const preset = characterProfiles.get(elements.characterPreset.value);
    if (!preset) return;
    elements.prompt.value = preset.prompt;
    document.querySelector('#negative').value = [BASE_NEGATIVE_PROMPT, preset.negative_prompt]
      .filter(Boolean)
      .join(', ');
    elements.lora.value = preset.lora_scale;
    elements.loraValue.textContent = preset.lora_scale.toFixed(2);
    document.querySelector('#cfg').value = preset.guidance_scale;
    elements.singleSubject.checked = preset.single_subject;
    elements.prompt.focus();
  });
  elements.characterReferenceFiles.addEventListener('change', uploadCharacterReferences);
  elements.poseReferenceFile.addEventListener('change', uploadPoseReference);
  elements.poseReferenceClear.addEventListener('click', clearPoseReference);
  [
    elements.referenceIpScale,
    elements.referenceFaceIpScale,
    elements.referenceFaceRefinementStrength,
  ].forEach((control) => control.addEventListener('input', updateReferenceScaleLabels));
  [
    elements.poseReferenceStrength,
    elements.poseReferenceZoom,
    elements.poseReferenceFocusX,
    elements.poseReferenceFocusY,
  ].forEach((control) => control.addEventListener('input', updatePoseReferencePreview));
  elements.poseReferenceStrength.addEventListener('input', updateQualityAdvice);
  document.querySelector('#refresh-history').addEventListener('click', refreshHistory);
  elements.form.addEventListener('submit', handleGeneration);
}

async function initializeApp() {
  bindEvents();
  try {
    await Promise.all([refreshStatus(), refreshHistory(), loadModels(), loadCharacterProfiles()]);
  } catch (error) {
    elements.status.textContent = `接続エラー: ${error.message}`;
    elements.activeModel.textContent = 'モデル情報を取得できません';
  }
}

initializeApp();
