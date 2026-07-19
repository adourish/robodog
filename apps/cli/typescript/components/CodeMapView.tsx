/**
 * Code Map View Component
 * React component for visualizing and interacting with code map
 */

import React, { useState, useEffect } from 'react';
import { CodeMapClient, FileMap, DefinitionResult, ContextResult } from '../CodeMapClient';

interface CodeMapViewProps {
  baseUrl: string;
  token: string;
}

export const CodeMapView: React.FC<CodeMapViewProps> = ({ baseUrl, token }) => {
  const [client] = useState(() => new CodeMapClient(baseUrl, token));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{
    fileCount: number;
    classCount: number;
    functionCount: number;
  } | null>(null);
  
  const [activeTab, setActiveTab] = useState<'scan' | 'find' | 'context'>('scan');
  
  // Scan tab state
  const [scanning, setScanning] = useState(false);
  
  // Find tab state
  const [searchName, setSearchName] = useState('');
  const [findResults, setFindResults] = useState<DefinitionResult[]>([]);
  
  // Context tab state
  const [taskDescription, setTaskDescription] = useState('');
  const [contextResults, setContextResults] = useState<ContextResult | null>(null);

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    try {
      const result = await client.scan();
      setStats({
        fileCount: result.file_count,
        classCount: result.class_count,
        functionCount: result.function_count,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setScanning(false);
    }
  };

  const handleFind = async () => {
    if (!searchName.trim()) return;
    
    setLoading(true);
    setError(null);
    try {
      const results = await client.findDefinition(searchName);
      setFindResults(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Find failed');
    } finally {
      setLoading(false);
    }
  };

  const handleGetContext = async () => {
    if (!taskDescription.trim()) return;
    
    setLoading(true);
    setError(null);
    try {
      const context = await client.getContext(taskDescription);
      setContextResults(context);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Context fetch failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="code-map-view">
      <div className="header">
        <h2>🗺️ Code Map</h2>
        {stats && (
          <div className="stats">
            <span>{stats.fileCount} files</span>
            <span>{stats.classCount} classes</span>
            <span>{stats.functionCount} functions</span>
          </div>
        )}
      </div>

      {error && (
        <div className="error-banner">
          ⚠️ {error}
        </div>
      )}

      <div className="tabs">
        <button
          className={activeTab === 'scan' ? 'active' : ''}
          onClick={() => setActiveTab('scan')}
        >
          Scan
        </button>
        <button
          className={activeTab === 'find' ? 'active' : ''}
          onClick={() => setActiveTab('find')}
        >
          Find
        </button>
        <button
          className={activeTab === 'context' ? 'active' : ''}
          onClick={() => setActiveTab('context')}
        >
          Context
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'scan' && (
          <ScanTab
            scanning={scanning}
            stats={stats}
            onScan={handleScan}
          />
        )}

        {activeTab === 'find' && (
          <FindTab
            searchName={searchName}
            setSearchName={setSearchName}
            loading={loading}
            results={findResults}
            onFind={handleFind}
          />
        )}

        {activeTab === 'context' && (
          <ContextTab
            taskDescription={taskDescription}
            setTaskDescription={setTaskDescription}
            loading={loading}
            results={contextResults}
            onGetContext={handleGetContext}
          />
        )}
      </div>
    </div>
  );
};

const ScanTab: React.FC<{
  scanning: boolean;
  stats: any;
  onScan: () => void;
}> = ({ scanning, stats, onScan }) => (
  <div className="scan-tab">
    <p>Scan your codebase to create a searchable map of classes, functions, and dependencies.</p>
    
    <button
      onClick={onScan}
      disabled={scanning}
      className="primary-button"
    >
      {scanning ? '⏳ Scanning...' : '🔍 Scan Codebase'}
    </button>

    {stats && (
      <div className="scan-results">
        <h3>Scan Results</h3>
        <div className="result-grid">
          <div className="result-card">
            <div className="result-value">{stats.fileCount}</div>
            <div className="result-label">Files Mapped</div>
          </div>
          <div className="result-card">
            <div className="result-value">{stats.classCount}</div>
            <div className="result-label">Classes Found</div>
          </div>
          <div className="result-card">
            <div className="result-value">{stats.functionCount}</div>
            <div className="result-label">Functions Found</div>
          </div>
        </div>
      </div>
    )}
  </div>
);

const FindTab: React.FC<{
  searchName: string;
  setSearchName: (name: string) => void;
  loading: boolean;
  results: DefinitionResult[];
  onFind: () => void;
}> = ({ searchName, setSearchName, loading, results, onFind }) => (
  <div className="find-tab">
    <p>Find where a class or function is defined in your codebase.</p>
    
    <div className="search-box">
      <input
        type="text"
        placeholder="Enter class or function name..."
        value={searchName}
        onChange={(e) => setSearchName(e.target.value)}
        onKeyPress={(e) => e.key === 'Enter' && onFind()}
      />
      <button onClick={onFind} disabled={loading || !searchName.trim()}>
        {loading ? '⏳' : '🔍'} Find
      </button>
    </div>

    {results.length > 0 && (
      <div className="results-list">
        <h3>Found {results.length} definition(s)</h3>
        {results.map((result, idx) => (
          <div key={idx} className="result-item">
            <div className="result-header">
              <span className="result-type">{result.type}</span>
              <span className="result-name">{result.name}</span>
            </div>
            <div className="result-location">
              📄 {result.file.split('/').pop()}:{result.line_start}
            </div>
            {result.docstring && (
              <div className="result-doc">{result.docstring}</div>
            )}
            {result.args && result.args.length > 0 && (
              <div className="result-args">
                Args: {result.args.join(', ')}
              </div>
            )}
          </div>
        ))}
      </div>
    )}

    {results.length === 0 && searchName && !loading && (
      <div className="no-results">
        No definitions found for "{searchName}"
      </div>
    )}
  </div>
);

const ContextTab: React.FC<{
  taskDescription: string;
  setTaskDescription: (desc: string) => void;
  loading: boolean;
  results: ContextResult | null;
  onGetContext: () => void;
}> = ({ taskDescription, setTaskDescription, loading, results, onGetContext }) => (
  <div className="context-tab">
    <p>Get relevant files for a task based on keywords and patterns.</p>
    
    <div className="task-input">
      <textarea
        placeholder="Describe your task (e.g., 'implement user authentication')..."
        value={taskDescription}
        onChange={(e) => setTaskDescription(e.target.value)}
        rows={3}
      />
      <button
        onClick={onGetContext}
        disabled={loading || !taskDescription.trim()}
        className="primary-button"
      >
        {loading ? '⏳ Analyzing...' : '🎯 Get Context'}
      </button>
    </div>

    {results && (
      <div className="context-results">
        <div className="context-header">
          <h3>Relevant Files ({results.total_files})</h3>
          <div className="keywords">
            Keywords: {results.keywords.join(', ')}
          </div>
        </div>

        <div className="files-list">
          {Object.entries(results.relevant_files).slice(0, 10).map(([filePath, info]) => (
            <div key={filePath} className="file-item">
              <div className="file-header">
                <span className="file-score">{info.score}</span>
                <span className="file-name">{filePath.split('/').pop()}</span>
              </div>
              <div className="file-path">{filePath}</div>
              <div className="file-details">
                {info.summary.classes.length > 0 && (
                  <span>Classes: {info.summary.classes.slice(0, 3).join(', ')}</span>
                )}
                {info.summary.functions.length > 0 && (
                  <span>Functions: {info.summary.functions.slice(0, 3).join(', ')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    )}
  </div>
);

export default CodeMapView;
