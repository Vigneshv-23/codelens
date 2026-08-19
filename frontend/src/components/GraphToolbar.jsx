import { memo } from 'react';

const relationshipTypes = ['calls', 'imports', 'contains', 'inherits', 'implements'];
const nodeTypes = ['function', 'method', 'class', 'interface', 'import', 'file'];

function ToggleGroup({ title, values, enabled, onToggle }) {
  return (
    <fieldset className="toolbar-group">
      <legend>{title}</legend>
      <div className="toggle-list">
        {values.map((value) => (
          <label key={value} className="toggle-label">
            <input type="checkbox" checked={enabled.has(value)} onChange={() => onToggle(value)} />
            <span>{value}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function GraphToolbar({
  query,
  onQueryChange,
  searchResults,
  onSearchSelect,
  viewMode,
  onOverview,
  onFocus,
  onExpand,
  onFit,
  selectedId,
  focusId,
  relationshipFilters,
  nodeFilters,
  onRelationshipToggle,
  onNodeToggle,
}) {
  return (
    <div className="graph-toolbar" aria-label="Graph controls">
      <div className="toolbar-row toolbar-primary">
        <label className="search-field">
          <span>Search symbols</span>
          <input type="search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Name or file path" />
        </label>
        {query && <span className="search-count">{searchResults.length} matches</span>}
        <div className="toolbar-actions" aria-label="Graph view controls">
          <button type="button" className={viewMode === 'overview' ? 'active' : ''} onClick={onOverview}>Overview</button>
          <button type="button" className={viewMode === 'focused' ? 'active' : ''} onClick={onFocus} disabled={!selectedId}>Focus</button>
          <button type="button" onClick={onExpand} disabled={!selectedId && !focusId}>Expand</button>
          <button type="button" onClick={onFit}>Fit view</button>
        </div>
      </div>
      {query && searchResults.length > 0 && (
        <ul className="search-results" aria-label="Search results">
          {searchResults.slice(0, 8).map((node) => (
            <li key={node.id}>
              <button type="button" onClick={() => onSearchSelect(node.id)}>
                <strong>{node.name}</strong>
                <span>{node.symbol_type} · {node.file_path}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <details className="filter-menu">
        <summary>Filters</summary>
        <div className="filter-popover">
          <ToggleGroup title="Relationships" values={relationshipTypes} enabled={relationshipFilters} onToggle={onRelationshipToggle} />
          <ToggleGroup title="Node types" values={nodeTypes} enabled={nodeFilters} onToggle={onNodeToggle} />
        </div>
      </details>
    </div>
  );
}

export default memo(GraphToolbar);
