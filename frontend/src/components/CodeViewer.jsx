import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-java';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-typescript';
import { getSource } from '../api';

const grammars = {
  python: Prism.languages.python,
  javascript: Prism.languages.javascript,
  typescript: Prism.languages.typescript,
  java: Prism.languages.java,
};

function highlightLine(line, language) {
  const grammar = grammars[language];
  return grammar ? Prism.highlight(line, grammar, language) : Prism.util.encode(line);
}

export default function CodeViewer({ analysisId, node, onBack }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const selectedLineRef = useRef(null);

  useEffect(() => {
    let active = true;
    setResult(null);
    setError('');
    getSource(analysisId, node.id)
      .then((source) => active && setResult(source))
      .catch((sourceError) => active && setError(sourceError.message));
    return () => { active = false; };
  }, [analysisId, node.id]);

  useLayoutEffect(() => {
    selectedLineRef.current?.scrollIntoView({ block: 'center' });
  }, [result]);

  if (error) {
    return <section className="code-viewer"><button type="button" className="code-viewer-back" onClick={onBack}>← Back to Graph</button><p className="error-message">{error}</p></section>;
  }

  const metadata = result?.symbol || node;
  const lines = result?.source.split('\n') || [];
  const sourceStartLine = result?.start_line || 1;

  return (
    <section className="code-viewer" aria-label="Code viewer">
      <header className="code-viewer-header">
        <button type="button" className="code-viewer-back" onClick={onBack}>← Back to Graph</button>
        <div>
          <p className="eyebrow">{metadata.file || node.file_path}</p>
          <h2>{metadata.name || node.name}</h2>
          <p className="code-viewer-location">{metadata.language || node.language} · Lines {metadata.start_line}–{metadata.end_line}</p>
        </div>
      </header>
      {!result ? <p className="loading-message">Loading source...</p> : (
        <div className="code-source" role="region" aria-label={`${metadata.file} source`}>
          <code>
            {lines.map((line, index) => {
              const lineNumber = sourceStartLine + index;
              const selected = lineNumber >= metadata.start_line && lineNumber <= metadata.end_line;
              return <span key={lineNumber} ref={selected && lineNumber === metadata.start_line ? selectedLineRef : null} className={`code-line${selected ? ' selected' : ''}`}><span className="line-number">{lineNumber}</span><span className="line-content" dangerouslySetInnerHTML={{ __html: highlightLine(line, metadata.language) }} /></span>;
            })}
          </code>
        </div>
      )}
    </section>
  );
}
