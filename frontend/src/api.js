async function throwApiError(response, fallbackMessage) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(fallbackMessage);
  }
  throw new Error(payload.detail || fallbackMessage);
}

export async function getHealth() {
  const response = await fetch('/api/health');
  if (!response.ok) await throwApiError(response, 'Backend health check failed');
  return response.json();
}

export async function analyzeRepository(file) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch('/api/analyze', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) await throwApiError(response, 'Repository analysis failed');
  const graph = await response.json();
  return { ...graph, analysis_id: graph.analysis_id || response.headers.get('X-Analysis-ID') };
}

export async function analyzeGithubRepository(url) {
  const response = await fetch('/api/analyze/github', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) await throwApiError(response, 'GitHub repository analysis failed');
  const graph = await response.json();
  return { ...graph, analysis_id: graph.analysis_id || response.headers.get('X-Analysis-ID') };
}

export async function getSource(analysisId, symbolId) {
  const response = await fetch(`/api/source/${encodeURIComponent(analysisId)}/${encodeURIComponent(symbolId)}`);
  if (!response.ok) await throwApiError(response, 'Source unavailable');
  return response.json();
}

export async function explainSymbol(analysisId, symbolId, action) {
  const response = await fetch('/api/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ analysis_id: analysisId, symbol_id: symbolId, action }),
  });
  if (!response.ok) await throwApiError(response, 'AI explanation failed');
  return response.json();
}
