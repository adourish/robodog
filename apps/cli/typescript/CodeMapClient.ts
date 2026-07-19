/**
 * Code Map Client for RoboDog React App
 * TypeScript client for code mapping features
 */

export interface FileMap {
  path: string;
  language: string;
  size: number;
  lines: number;
  classes: string[];
  functions: string[];
  imports: string[];
  dependencies: string[];
  docstring?: string;
}

export interface DefinitionResult {
  type: 'class' | 'function';
  name: string;
  file: string;
  line_start: number;
  line_end: number;
  docstring?: string;
  args?: string[];
}

export interface ContextResult {
  task: string;
  keywords: string[];
  relevant_files: {
    [filePath: string]: {
      score: number;
      summary: FileMap;
    };
  };
  total_files: number;
}

export interface MapIndex {
  classes: { [name: string]: number };
  functions: { [name: string]: number };
  imports: { [module: string]: number };
}

export interface ScanResult {
  file_count: number;
  class_count: number;
  function_count: number;
}

export class CodeMapClient {
  private baseUrl: string;
  private token: string;

  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl;
    this.token = token;
  }

  private async request<T>(op: string, payload: any = {}): Promise<T> {
    const response = await fetch(this.baseUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ op, payload }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    
    if (data.status !== 'ok') {
      throw new Error(data.error || 'Unknown error');
    }

    return data as T;
  }

  /**
   * Scan codebase and create map
   */
  async scan(extensions?: string[]): Promise<ScanResult> {
    const result = await this.request<{
      status: string;
      file_count: number;
      class_count: number;
      function_count: number;
    }>('MAP_SCAN', { extensions });

    return {
      file_count: result.file_count,
      class_count: result.class_count,
      function_count: result.function_count,
    };
  }

  /**
   * Find definition of a class or function
   */
  async findDefinition(name: string): Promise<DefinitionResult[]> {
    const result = await this.request<{
      status: string;
      results: DefinitionResult[];
    }>('MAP_FIND', { name });

    return result.results;
  }

  /**
   * Get context for a task
   */
  async getContext(
    taskDescription: string,
    includePatterns?: string[]
  ): Promise<ContextResult> {
    const result = await this.request<{
      status: string;
      context: ContextResult;
    }>('MAP_CONTEXT', {
      task_description: taskDescription,
      include_patterns: includePatterns,
    });

    return result.context;
  }

  /**
   * Get file summary
   */
  async getFileSummary(filePath: string): Promise<FileMap> {
    const result = await this.request<{
      status: string;
      summary: FileMap;
    }>('MAP_SUMMARY', { file_path: filePath });

    return result.summary;
  }

  /**
   * Find module usages
   */
  async findUsages(module: string): Promise<string[]> {
    const result = await this.request<{
      status: string;
      module: string;
      files: string[];
    }>('MAP_USAGES', { module });

    return result.files;
  }

  /**
   * Save map to file
   */
  async saveMap(outputPath: string = 'codemap.json'): Promise<string> {
    const result = await this.request<{
      status: string;
      path: string;
    }>('MAP_SAVE', { output_path: outputPath });

    return result.path;
  }

  /**
   * Load map from file
   */
  async loadMap(inputPath: string = 'codemap.json'): Promise<number> {
    const result = await this.request<{
      status: string;
      path: string;
      file_count: number;
    }>('MAP_LOAD', { input_path: inputPath });

    return result.file_count;
  }

  /**
   * Get index statistics
   */
  async getIndex(): Promise<{
    index: MapIndex;
    total_files: number;
  }> {
    const result = await this.request<{
      status: string;
      index: MapIndex;
      total_files: number;
    }>('MAP_INDEX', {});

    return {
      index: result.index,
      total_files: result.total_files,
    };
  }
}

/**
 * React Hook for Code Map
 */
export function useCodeMap(baseUrl: string, token: string) {
  const client = new CodeMapClient(baseUrl, token);

  return {
    scan: (extensions?: string[]) => client.scan(extensions),
    findDefinition: (name: string) => client.findDefinition(name),
    getContext: (taskDescription: string, patterns?: string[]) =>
      client.getContext(taskDescription, patterns),
    getFileSummary: (filePath: string) => client.getFileSummary(filePath),
    findUsages: (module: string) => client.findUsages(module),
    saveMap: (path?: string) => client.saveMap(path),
    loadMap: (path?: string) => client.loadMap(path),
    getIndex: () => client.getIndex(),
  };
}

/**
 * Helper function to format file size
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Helper function to get language icon
 */
export function getLanguageIcon(language: string): string {
  const icons: { [key: string]: string } = {
    python: '🐍',
    javascript: '📜',
    typescript: '📘',
  };
  return icons[language] || '📄';
}

/**
 * Helper function to format line range
 */
export function formatLineRange(start: number, end: number): string {
  if (start === end) return `L${start}`;
  return `L${start}-${end}`;
}

export default CodeMapClient;
