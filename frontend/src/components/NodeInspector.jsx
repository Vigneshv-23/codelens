import MarkdownAnswer from './MarkdownAnswer';

const MAX_ITEMS = 5;

function RelationshipList({ title, relationships, direction, indexes, onSelect, onFocus }) {
  const visible = relationships.slice(0, MAX_ITEMS);
  const remaining = relationships.length - visible.length;
  return (
    <section className="inspector-section">
      <div className="inspector-section-heading"><h3>{title}</h3><span>{relationships.length}</span></div>
      {relationships.length === 0 ? (
        <p className="muted">None</p>
      ) : (
        <ul className="relationship-list">
          {visible.map((relationship) => {
            const targetId = direction === 'outgoing' ? relationship.target : relationship.source;
            const target = targetId ? indexes.nodesById.get(targetId) : null;
            return (
              <li key={relationship.id}>
                <button type="button" className="relationship-link" onClick={() => target && onSelect(target.id)} disabled={!target}>
                  <strong>{relationship.relationship_type}</strong>
                  <span>{target?.name || relationship.detail || 'Unresolved'}</span>
                  {relationship.target === null && <em>unresolved</em>}
                </button>
                {target && <button type="button" className="mini-action" onClick={() => onFocus(target.id)}>Focus</button>}
              </li>
            );
          })}
        </ul>
      )}
      {remaining > 0 && <p className="more-items">+ {remaining} more</p>}
    </section>
  );
}

function groupByType(relationships) {
  return relationships.reduce((groups, relationship) => {
    const key = relationship.relationship_type;
    if (!groups[key]) groups[key] = [];
    groups[key].push(relationship);
    return groups;
  }, {});
}

export default function NodeInspector({ node, relationships, indexes, onSelect, onFocus, onExpand, onInspectCode, onAiAction, aiState }) {
  if (!node) {
    return <aside className="inspector empty-inspector"><p>Select a node to inspect its source metadata and relationships.</p></aside>;
  }

  const dependencies = indexes.outgoing.get(node.id) || [];
  const dependents = indexes.incoming.get(node.id) || [];
  const calls = dependencies.filter((relationship) => relationship.relationship_type === 'calls');
  const calledBy = dependents.filter((relationship) => relationship.relationship_type === 'calls');
  const otherDependencies = dependencies.filter((relationship) => relationship.relationship_type !== 'calls');
  const otherDependents = dependents.filter((relationship) => relationship.relationship_type !== 'calls');
  const parent = node.parent_id ? indexes.nodesById.get(node.parent_id) : null;

  const canInspect = node.node_type === 'symbol' && node.file_path && node.language && Number.isInteger(node.start_line) && Number.isInteger(node.end_line);

  return (
    <aside className="inspector">
      <div className="inspector-heading"><p className="eyebrow">Selected symbol</p><h2 title={node.name}>{node.name}</h2><span className="inspector-type">{node.symbol_type}</span></div>
      <section className="inspector-section inspector-overview"><div className="inspector-section-heading"><h3>Overview</h3></div><dl className="metadata-list">
        <div><dt>Language</dt><dd>{node.language || '—'}</dd></div>
        <div><dt>File</dt><dd title={node.file_path}>{node.file_path}</dd></div>
        <div><dt>Location</dt><dd>{node.start_line ? `Lines ${node.start_line}–${node.end_line}` : '—'}{node.start_column !== null && node.start_column !== undefined ? ` · Columns ${node.start_column}–${node.end_column}` : ''}</dd></div>
        <div><dt>Parent</dt><dd>{parent ? <button type="button" className="metadata-link" onClick={() => onSelect(parent.id)}>{parent.name}</button> : '—'}</dd></div>
        <div><dt>Exported</dt><dd>{node.exported === null || node.exported === undefined ? '—' : node.exported ? 'Yes' : 'No'}</dd></div>
      </dl></section>
      <section className="inspector-section inspector-actions-section"><div className="inspector-section-heading"><h3>Actions</h3></div><div className="inspector-actions"><button type="button" onClick={() => onFocus(node.id)}>Focus on node</button><button type="button" onClick={() => onExpand(node.id)}>Expand neighbors</button>{canInspect && <button type="button" className="primary-action" onClick={() => onInspectCode(node)}>Inspect Code</button>}</div></section>
      {canInspect && <section className="inspector-section ai-section"><div className="inspector-section-heading"><h3>AI assistance</h3><span>Grounded in this symbol</span></div><div className="ai-actions"><button type="button" className={aiState?.action === 'explain' ? 'active' : ''} disabled={aiState?.loading} onClick={() => onAiAction('explain', node)}>Explain this</button><button type="button" className={aiState?.action === 'how_it_works' ? 'active' : ''} disabled={aiState?.loading} onClick={() => onAiAction('how_it_works', node)}>How does this work?</button><button type="button" className={aiState?.action === 'impact' ? 'active' : ''} disabled={aiState?.loading} onClick={() => onAiAction('impact', node)}>Impact analysis</button></div>{aiState?.loading && <p className="loading-message"><span className="loading-spinner" aria-hidden="true" />Analyzing code...</p>}{aiState?.error && <p className="error-message" role="alert"><strong>AI unavailable</strong><span>{aiState.error}</span></p>}{aiState?.response && <div className="ai-response"><MarkdownAnswer content={aiState.response.answer} />{aiState.response.context?.partial && <p className="muted">Bounded context: {(aiState.response.context.truncated || []).join(', ')}.</p>}</div>}</section>}
      <div className="inspector-section relationship-section"><div className="inspector-section-heading"><h3>Relationships</h3></div><RelationshipList title="Dependencies" direction="outgoing" relationships={otherDependencies} indexes={indexes} onSelect={onSelect} onFocus={onFocus} /><RelationshipList title="Dependents" direction="incoming" relationships={otherDependents} indexes={indexes} onSelect={onSelect} onFocus={onFocus} /><RelationshipList title="Calls" direction="outgoing" relationships={calls} indexes={indexes} onSelect={onSelect} onFocus={onFocus} /><RelationshipList title="Called by" direction="incoming" relationships={calledBy} indexes={indexes} onSelect={onSelect} onFocus={onFocus} /></div>
    </aside>
  );
}

export { groupByType };
