export function createImageCard(image, onUseAsReference, onSaveEvaluation) {
  const card = document.createElement('div');
  card.className = 'image-card';

  const imageElement = document.createElement('img');
  imageElement.src = image.image_url;
  imageElement.alt = '生成画像';

  const footer = document.createElement('div');
  const seed = document.createElement('span');
  seed.className = 'seed';
  seed.textContent = `seed: ${image.seed}`;
  const download = document.createElement('a');
  download.className = 'download';
  download.href = `/download/${image.filename}`;
  download.download = '';
  download.textContent = 'ダウンロード';
  const useAsReference = document.createElement('button');
  useAsReference.type = 'button';
  useAsReference.className = 'use-as-reference';
  useAsReference.dataset.useAsReference = image.filename;
  useAsReference.textContent = '基準画像に追加';
  if (onUseAsReference) {
    useAsReference.addEventListener('click', () => onUseAsReference(useAsReference));
  }

  footer.append(seed, download, useAsReference);
  const evaluation = document.createElement('details');
  evaluation.className = 'evaluation';
  evaluation.innerHTML = `<summary>品質を評価</summary>
    <label>同一性 <select data-score="identity"><option>1</option><option>2</option><option>3</option><option>4</option><option selected>5</option></select></label>
    <label>画風 <select data-score="style"><option>1</option><option>2</option><option>3</option><option>4</option><option selected>5</option></select></label>
    <label>ポーズ <select data-score="pose"><option>1</option><option>2</option><option>3</option><option>4</option><option selected>5</option></select></label>
    <input data-evaluation-notes maxlength="500" placeholder="比較条件・気づき（任意）" />
    <button type="button" data-save-evaluation="${image.filename}">評価を保存</button>
    <small data-evaluation-status></small>`;
  const evaluationButton = evaluation.querySelector('[data-save-evaluation]');
  if (onSaveEvaluation) {
    evaluationButton.addEventListener('click', () => onSaveEvaluation(evaluationButton));
  }
  card.append(imageElement, footer, evaluation);
  return card;
}

export function createLoadingMessage() {
  const loading = document.createElement('article');
  loading.className = 'assistant-message loading';
  loading.innerHTML = '<div class="avatar">✦</div><p>画像を生成しています…</p>';
  return loading;
}

export function createUserMessage(template, prompt) {
  const fragment = template.content.cloneNode(true);
  fragment.querySelector('.bubble').textContent = prompt;
  return fragment;
}

export function createResultMessage(template, images, onUseAsReference, onSaveEvaluation) {
  const fragment = template.content.cloneNode(true);
  const grid = fragment.querySelector('.result-grid');
  images.forEach((image) =>
    grid.append(createImageCard(image, onUseAsReference, onSaveEvaluation)),
  );
  return {fragment, grid};
}
