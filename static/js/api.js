const JSON_HEADERS = {'Content-Type': 'application/json'};

export class NetworkError extends Error {
  constructor() {
    super('PCに接続できません。同じWi-FiとPC側の起動状態を確認してください。');
    this.name = 'NetworkError';
  }
}

async function requestJson(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error instanceof TypeError) throw new NetworkError();
    throw error;
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || 'リクエストに失敗しました');
  return payload;
}

export const api = {
  getStatus: () => requestJson('/api/status'),
  getModels: () => requestJson('/api/models'),
  getCharacterProfiles: () => requestJson('/api/character-profiles'),
  uploadReferenceImage: (file) => requestJson('/api/reference-images', {
    method: 'POST',
    headers: {'Content-Type': file.type},
    body: file,
  }),
  createReferenceFromHistory: (filename) => requestJson(
    `/api/reference-images/from-history/${encodeURIComponent(filename)}`,
    {method: 'POST'},
  ),
  getHistory: () => requestJson('/api/history'),
  saveEvaluation: (filename, payload) => requestJson(
    `/api/history/${encodeURIComponent(filename)}/evaluation`,
    {method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(payload)},
  ),
  createJob: (payload) => requestJson('/api/jobs', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  }),
  getJob: (jobId) => requestJson(`/api/jobs/${jobId}`),
  cancelJob: (jobId) => requestJson(`/api/jobs/${jobId}/cancel`, {method: 'POST'}),
};
