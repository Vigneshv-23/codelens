import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useNodesState,
  ReactFlowProvider,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { analyzeGithubRepository, analyzeRepository, explainSymbol, getHealth } from './api';
import CodeNode from './components/CodeNode';
import GraphToolbar from './components/GraphToolbar';
import NodeInspector from './components/NodeInspector';
import CodeViewer from './components/CodeViewer';

const nodeTypes = { code: CodeNode };
const LARGE_GRAPH_THRESHOLD = 180;
const MINIMAP_THRESHOLD = 300;
const relationshipColors = {
  calls: '#be123c',
  imports: '#d97706',
  contains: '#2563eb',
  inherits: '#9333ea',
  implements: '#0f766e',
};
const ALL_RELATIONSHIPS = new Set(Object.keys(relationshipColors));
const OVERVIEW_RELATIONSHIPS = new Set(['imports', 'contains', 'inherits', 'implements', 'calls']);
const ALL_NODE_TYPES = new Set(['function', 'method', 'class', 'interface', 'import', 'file']);

function fileKey(filePath) {
  return `file:${filePath}`;
}

function fileName(filePath) {
  return filePath.split('/').pop() || filePath;
}

function primarySymbol(nodes) {
  return sortNodes(nodes).find((node) => ['class', 'interface', 'function', 'method'].includes(node.symbol_type))
    || sortNodes(nodes).find((node) => node.node_type !== 'file' && !node.name.startsWith('import '))
    || sortNodes(nodes)[0]
    || null;
}

function sortNodes(nodes) {
  return [...nodes].sort((a, b) => (
    (a.file_path || '').localeCompare(b.file_path || '')
    || (a.start_line || 0) - (b.start_line || 0)
    || (a.start_column || 0) - (b.start_column || 0)
    || a.id.localeCompare(b.id)
  ));
}

function createIndexes(graph) {
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const outgoing = new Map();
  const incoming = new Map();
  const adjacency = new Map();
  const nodesByFile = new Map();

  graph.nodes.forEach((node) => {
    if (!nodesByFile.has(node.file_path)) nodesByFile.set(node.file_path, []);
    nodesByFile.get(node.file_path).push(node);
    outgoing.set(node.id, []);
    incoming.set(node.id, []);
    adjacency.set(node.id, new Set());
  });

  graph.edges.forEach((edge) => {
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
    outgoing.get(edge.source).push(edge);
    if (edge.target !== null) {
      if (!incoming.has(edge.target)) incoming.set(edge.target, []);
      incoming.get(edge.target).push(edge);
      if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set());
      if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set());
      adjacency.get(edge.source).add(edge.target);
      adjacency.get(edge.target).add(edge.source);
    }
  });

  return { nodesById, outgoing, incoming, adjacency, nodesByFile };
}

function createOverview(graph, indexes) {
  const files = [...indexes.nodesByFile.keys()].sort((a, b) => a.localeCompare(b));
  const nodes = files.map((path) => ({
    id: fileKey(path),
    name: fileName(path),
    label: path,
    symbol_type: 'file',
    language: null,
    file_path: path,
    start_line: null,
    end_line: null,
    start_column: null,
    end_column: null,
    parent_id: null,
    exported: null,
    node_type: 'file',
    isOverview: true,
  }));
  const edgeMap = new Map();
  graph.edges.forEach((edge) => {
    if (edge.target === null) return;
    const sourceNode = indexes.nodesById.get(edge.source);
    const targetNode = indexes.nodesById.get(edge.target);
    if (!sourceNode || !targetNode || sourceNode.file_path === targetNode.file_path) return;
    const key = `${sourceNode.file_path}|${targetNode.file_path}|${edge.relationship_type}`;
    if (!edgeMap.has(key)) {
      edgeMap.set(key, {
        ...edge,
        id: `overview:${key}`,
        source: fileKey(sourceNode.file_path),
        target: fileKey(targetNode.file_path),
        detail: `${edge.relationship_type} · ${sourceNode.file_path} → ${targetNode.file_path}`,
        isOverview: true,
      });
    }
  });
  return { nodes, edges: [...edgeMap.values()] };
}

function neighborhoodIds(indexes, focusId, depth) {
  if (!focusId) return new Set();
  const ids = new Set([focusId]);
  let frontier = new Set([focusId]);
  for (let level = 0; level < depth; level += 1) {
    const next = new Set();
    frontier.forEach((id) => {
      (indexes.adjacency.get(id) || []).forEach((neighbor) => {
        if (!ids.has(neighbor)) {
          ids.add(neighbor);
          next.add(neighbor);
        }
      });
      const parent = indexes.nodesById.get(id)?.parent_id;
      if (parent && indexes.nodesById.has(parent) && !ids.has(parent)) {
        ids.add(parent);
        next.add(parent);
      }
    });
    frontier = next;
  }
  return ids;
}

function toFlowNode(node, position, selectedId, focusId) {
  return {
    id: node.id,
    type: 'code',
    position,
    selected: node.id === selectedId,
    className: selectedId && node.id !== selectedId ? 'dimmed' : '',
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { ...node, isFocus: node.id === focusId },
  };
}

function layoutNodes(nodes, mode, focusId, selectedId) {
  const ordered = sortNodes(nodes);
  if (mode === 'focused') {
    const root = ordered.find((node) => node.id === focusId) || ordered.find((node) => node.id === selectedId) || ordered[0];
    if (!root) return [];
    const rest = ordered.filter((node) => node.id !== root.id);
    const columns = Math.max(1, Math.ceil(Math.sqrt(rest.length)));
    const positions = new Map([[root.id, { x: 400, y: 260 }]]);
    rest.forEach((node, index) => positions.set(node.id, {
      x: (index % columns) * 260,
      y: Math.floor(index / columns) * 150 + 40,
    }));
    return ordered.map((node) => toFlowNode(node, positions.get(node.id), selectedId, focusId));
  }
  const columns = Math.max(1, Math.ceil(Math.sqrt(ordered.length)));
  return ordered.map((node, index) => toFlowNode(node, {
    x: (index % columns) * 260,
    y: Math.floor(index / columns) * 150,
  }, selectedId, focusId));
}

function mapEdges(edges, { largeGraph, selectedId, focused }) {
  return edges.filter((edge) => edge.target !== null).map((edge) => {
    const highlighted = Boolean(selectedId && (edge.source === selectedId || edge.target === selectedId));
    const color = relationshipColors[edge.relationship_type] || '#64748b';
    const showLabel = Boolean((focused || highlighted) && (!largeGraph || highlighted));
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: 'source',
      targetHandle: 'target',
      label: showLabel ? edge.relationship_type : undefined,
      data: edge,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed },
       style: { stroke: color, strokeWidth: highlighted ? 2.5 : 2, opacity: selectedId && !highlighted ? 0.2 : 0.9 },
      labelStyle: { fill: color, fontSize: 9, fontWeight: 600 },
      labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.85 },
    };
  });
}

function GraphFlow({ nodes: sourceNodes, edges: sourceEdges, graphSize, selectedId, focusId, onSelect, fitRequest, focused, layoutMode }) {
  const preparedNodes = useMemo(() => layoutNodes(sourceNodes, layoutMode, focusId, selectedId), [focusId, layoutMode, selectedId, sourceNodes]);
  const preparedEdges = useMemo(() => mapEdges(sourceEdges, { largeGraph: graphSize > LARGE_GRAPH_THRESHOLD, selectedId, focused }), [focused, graphSize, selectedId, sourceEdges]);
  const { fitView } = useReactFlow();
  const highlightedNodes = useMemo(() => preparedNodes.map((node) => ({
    ...node,
    selected: node.id === selectedId,
    className: selectedId && node.id !== selectedId ? 'dimmed' : '',
    data: { ...node.data, isFocus: node.id === focusId },
  })), [focusId, preparedNodes, selectedId]);
  const [displayedNodes, setDisplayedNodes, handleNodesChange] = useNodesState(highlightedNodes);

  useEffect(() => {
    setDisplayedNodes(highlightedNodes);
  }, [highlightedNodes, setDisplayedNodes]);

  useEffect(() => {
    if (fitRequest) requestAnimationFrame(() => fitView({ padding: 0.2, duration: 0 }));
  }, [fitRequest, fitView]);

  const handleNodeClick = useCallback((event, node) => {
    onSelect(node.id, node.data);
  }, [onSelect]);

  const handlePaneClick = useCallback(() => onSelect(null, null), [onSelect]);
  const handleFlowInit = useCallback((instance) => {
    requestAnimationFrame(() => instance.fitView({ padding: 0.2, duration: 0 }));
  }, []);

  return (
    <ReactFlow
      nodes={displayedNodes}
      edges={preparedEdges}
      nodeTypes={nodeTypes}
      onInit={handleFlowInit}
      onNodesChange={handleNodesChange}
      onNodeClick={handleNodeClick}
      onPaneClick={handlePaneClick}
      panOnDrag={[0, 1, 2]}
      selectionOnDrag={false}
      minZoom={0.1}
      maxZoom={2}
      nodesFocusable
      edgesFocusable
    >
      <Background color="#dbe3ee" gap={24} size={1} />
      <Controls showInteractive />
      {graphSize <= MINIMAP_THRESHOLD && <MiniMap nodeColor={(node) => node.data.node_type === 'file' ? '#d97706' : '#2563eb'} pannable zoomable />}
      <button type="button" className="fit-button" onClick={() => fitView({ padding: 0.2, duration: 0 })}>Fit view</button>
    </ReactFlow>
  );
}

function GraphCanvas(props) {
  return <ReactFlowProvider><GraphFlow {...props} /></ReactFlowProvider>;
}

export default function App() {
  const [status, setStatus] = useState('checking');
  const [githubUrl, setGithubUrl] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [graph, setGraph] = useState(null);
  const [analysisId, setAnalysisId] = useState(null);
  const [codeTarget, setCodeTarget] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [focusId, setFocusId] = useState(null);
  const [viewMode, setViewMode] = useState('overview');
  const [expansionDepth, setExpansionDepth] = useState(1);
  const [fitRequest, setFitRequest] = useState(0);
  const [query, setQuery] = useState('');
  const [relationshipFilters, setRelationshipFilters] = useState(new Set(OVERVIEW_RELATIONSHIPS));
  const [nodeFilters, setNodeFilters] = useState(ALL_NODE_TYPES);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [aiState, setAiState] = useState({ action: null, loading: false, response: null, error: '' });

  useEffect(() => {
    getHealth().then((health) => setStatus(health.status)).catch(() => setStatus('unavailable'));
  }, []);

  const indexes = useMemo(() => graph ? createIndexes(graph) : null, [graph]);
  const overview = useMemo(() => graph && indexes ? createOverview(graph, indexes) : null, [graph, indexes]);
  const isLargeGraph = Boolean(graph && graph.nodes.length > LARGE_GRAPH_THRESHOLD);

  const searchResults = useMemo(() => {
    if (!indexes || !query.trim()) return [];
    const term = query.trim().toLowerCase();
    return sortNodes(graph.nodes.filter((node) => [node.name, node.file_path, node.symbol_type, node.language, node.label].filter(Boolean).some((value) => value.toLowerCase().includes(term))))
      .sort((a, b) => Number(a.name.toLowerCase() !== term) - Number(b.name.toLowerCase() !== term) || a.name.localeCompare(b.name));
  }, [graph, indexes, query]);

  const visible = useMemo(() => {
    if (!graph || !indexes || !overview) return { nodes: [], edges: [] };
    const activeEdges = graph.edges.filter((edge) => relationshipFilters.has(edge.relationship_type) && edge.target !== null);
    if (viewMode === 'overview') {
      const allowedFiles = new Set(overview.nodes.filter((node) => nodeFilters.has('file')).map((node) => node.file_path));
      return {
        nodes: overview.nodes.filter((node) => allowedFiles.has(node.file_path)),
        edges: overview.edges.filter((edge) => relationshipFilters.has(edge.relationship_type) && allowedFiles.has(edge.source.slice(5)) && allowedFiles.has(edge.target.slice(5))),
      };
    }
    const ids = neighborhoodIds({ ...indexes, adjacency: createAdjacency(activeEdges) }, focusId, expansionDepth);
    const nodes = graph.nodes.filter((node) => ids.has(node.id) && (node.id === focusId || nodeFilters.has(node.symbol_type) || nodeFilters.has(node.node_type === 'file' ? 'file' : node.node_type)));
    const allowedIds = new Set(nodes.map((node) => node.id));
    return { nodes, edges: activeEdges.filter((edge) => allowedIds.has(edge.source) && allowedIds.has(edge.target)) };
  }, [expansionDepth, focusId, graph, indexes, nodeFilters, overview, relationshipFilters, selectedId, viewMode]);

  const selectedVisibleNode = selectedNode || (selectedId && indexes?.nodesById.get(selectedId));

  const inspectCode = useCallback((node) => {
    setCodeTarget(node);
  }, []);

  const runAiAction = useCallback(async (action, node) => {
    if (!analysisId || !node || node.node_type !== 'symbol') return;
    setAiState({ action, loading: true, response: null, error: '' });
    try {
      const response = await explainSymbol(analysisId, node.id, action);
      setAiState({ action, loading: false, response, error: '' });
    } catch (aiError) {
      setAiState({ action, loading: false, response: null, error: aiError.message });
    }
  }, [analysisId]);

  const selectNode = useCallback((id, node) => {
    setAiState({ action: null, loading: false, response: null, error: '' });
    if (!id) {
      setSelectedId(null);
      setSelectedNode(null);
      return;
    }
    if (id.startsWith('file:')) {
      const path = id.slice(5);
      const symbol = primarySymbol(indexes?.nodesByFile.get(path) || []);
      setSelectedId(id);
      setSelectedNode(symbol);
      return;
    }
    setSelectedId(id);
    setSelectedNode(node || indexes?.nodesById.get(id) || null);
  }, [indexes]);

  const enableCalls = useCallback(() => {
    setRelationshipFilters((current) => {
      const next = new Set(current);
      next.add('calls');
      return next;
    });
  }, []);

  const focusNode = useCallback(() => {
    const rootId = selectedId?.startsWith('file:') ? selectedNode?.id : selectedId;
    if (!rootId) return;
    enableCalls();
    setSelectedId(rootId);
    setFocusId(rootId);
    setViewMode('focused');
    setExpansionDepth(1);
  }, [enableCalls, selectedId, selectedNode]);

  const openSearchResult = useCallback((id) => {
    const node = indexes?.nodesById.get(id);
    if (viewMode === 'overview' && node) {
      selectNode(fileKey(node.file_path), primarySymbol(indexes?.nodesByFile.get(node.file_path) || []));
    } else {
      selectNode(id, node);
    }
    setFitRequest((request) => request + 1);
  }, [indexes, selectNode, viewMode]);

  const returnOverview = useCallback(() => {
    setViewMode('overview');
    setFocusId(null);
    setExpansionDepth(1);
  }, []);

  const expandNeighbors = useCallback((requestedId) => {
    const rootId = requestedId || focusId || (selectedId?.startsWith('file:') ? selectedNode?.id : selectedId);
    if (!rootId) return;
    const rootNode = indexes?.nodesById.get(rootId);
    if (!rootNode) return;
    enableCalls();
    setSelectedId(rootId);
    setSelectedNode(rootNode);
    setFocusId(rootId);
    setViewMode('focused');
    setExpansionDepth((depth) => (focusId === rootId ? depth + 1 : 1));
    setFitRequest((request) => request + 1);
  }, [enableCalls, focusId, indexes, selectedId, selectedNode]);

  const toggleFilter = useCallback((setter) => (value) => setter((current) => {
    const next = new Set(current);
    if (next.has(value)) next.delete(value); else next.add(value);
    return next;
  }), []);

  async function submitAnalysis(action) {
    setLoading(true);
    setError('');
    try {
      const result = await action();
      setGraph(result);
      setAnalysisId(result.analysis_id);
      setCodeTarget(null);
      setSelectedId(null);
      setSelectedNode(null);
      setFocusId(null);
      setAiState({ action: null, loading: false, response: null, error: '' });
      setViewMode('overview');
      setExpansionDepth(1);
    } catch (analysisError) {
      setError(analysisError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={graph ? 'app-shell has-graph' : 'app-shell'}>
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">CL</div>
          <div>
            <p className="eyebrow">Developer workspace</p>
            <h1>CodeLens</h1>
          </div>
        </div>
        <div className="header-context">
          {graph && <div className="analysis-summary"><span>{graph.nodes.length} nodes</span><span>{graph.edges.length} relationships</span></div>}
          <p className="backend-status"><span className={status === 'healthy' ? 'status-dot healthy' : 'status-dot'} />Backend {status}</p>
        </div>
      </header>
      <section className="analysis-bar" aria-label="Repository analysis">
        <div className="analysis-section-heading"><p className="eyebrow">Repository</p><span>Analyze a GitHub URL or local ZIP</span></div>
        <form className="github-form" onSubmit={(event) => { event.preventDefault(); submitAnalysis(() => analyzeGithubRepository(githubUrl)); }}>
          <label htmlFor="github-url">GitHub repository URL</label>
          <div className="control-row"><input id="github-url" type="url" value={githubUrl} onChange={(event) => setGithubUrl(event.target.value)} placeholder="https://github.com/user/repository" required /><button type="submit" disabled={loading}>Analyze GitHub</button></div>
        </form>
        <span className="form-divider" aria-hidden="true">or</span>
        <form className="zip-form" onSubmit={(event) => { event.preventDefault(); submitAnalysis(() => analyzeRepository(selectedFile)); }}>
          <label htmlFor="zip-file">ZIP repository</label>
          <div className="control-row"><input id="zip-file" type="file" accept=".zip,application/zip" onChange={(event) => setSelectedFile(event.target.files[0] || null)} required /><button type="submit" disabled={loading}>Analyze ZIP</button></div>
        </form>
      </section>
      {error && <p className="error-message" role="alert"><strong>Analysis failed</strong><span>{error}</span></p>}
      {loading && <p className="loading-message"><span className="loading-spinner" aria-hidden="true" />Analyzing repository and building its graph...</p>}
      {graph ? codeTarget ? (
        <CodeViewer analysisId={analysisId} node={codeTarget} onBack={() => setCodeTarget(null)} />
      ) : (
        <section className="workspace" aria-label="Interactive code graph">
          <div className="graph-viewport">
            <GraphToolbar
              query={query}
              onQueryChange={setQuery}
              searchResults={searchResults}
              onSearchSelect={openSearchResult}
              viewMode={viewMode}
              onOverview={returnOverview}
              onFocus={focusNode}
              onExpand={expandNeighbors}
              onFit={() => setFitRequest((request) => request + 1)}
              selectedId={selectedId}
              focusId={focusId}
              expansionDepth={expansionDepth}
              relationshipFilters={relationshipFilters}
              nodeFilters={nodeFilters}
              onRelationshipToggle={toggleFilter(setRelationshipFilters)}
              onNodeToggle={toggleFilter(setNodeFilters)}
            />
            <GraphCanvas
              nodes={visible.nodes}
              edges={visible.edges}
              graphSize={graph.nodes.length}
              selectedId={selectedId}
              focusId={focusId}
              onSelect={selectNode}
              focused={viewMode === 'focused'}
              layoutMode={viewMode === 'focused' ? 'focused' : 'overview'}
              fitRequest={fitRequest}
            />
          </div>
          <NodeInspector
            node={selectedVisibleNode}
            relationships={graph.edges}
            indexes={indexes}
            onSelect={selectNode}
            onExpand={expandNeighbors}
            onInspectCode={inspectCode}
            onAiAction={runAiAction}
            aiState={aiState}
            onFocus={(id) => { selectNode(id); setFocusId(id); setViewMode('focused'); setExpansionDepth(1); enableCalls(); }}
          />
        </section>
      ) : (
        <section className="empty-state"><p className="eyebrow">Graph workspace</p><h2>Analyze a repository to explore its structure.</h2><p>Symbols become nodes. Imports, inheritance, implementation, containment, and calls become relationships you can navigate.</p></section>
      )}
    </main>
  );
}

function createAdjacency(edges) {
  const adjacency = new Map();
  edges.forEach((edge) => {
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set());
    if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set());
    adjacency.get(edge.source).add(edge.target);
    adjacency.get(edge.target).add(edge.source);
  });
  return adjacency;
}
