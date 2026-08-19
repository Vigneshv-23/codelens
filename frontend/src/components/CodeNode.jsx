import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';

function CodeNode({ data, selected }) {
  return (
    <article className={`code-node ${data.node_type === 'file' ? 'file-node' : ''} ${data.isFocus ? 'focus-node' : ''} ${selected ? 'selected' : ''}`}>
      <Handle id="target" type="target" position={Position.Left} />
      <div className="code-node-title" title={data.name}>{data.name}</div>
      <div className="code-node-meta">
        <span>{data.symbol_type}</span>
        {data.language && <span>{data.language}</span>}
      </div>
      <div className="code-node-file" title={data.file_path}>{data.file_path}</div>
      <Handle id="source" type="source" position={Position.Right} />
    </article>
  );
}

export default memo(CodeNode);
