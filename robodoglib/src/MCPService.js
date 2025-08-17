
import { FormatService } from './FormatService';
import { ConsoleService } from './ConsoleService';
import { ProviderService } from './ProviderService';
const formatService = new FormatService();
const consoleService = new ConsoleService();
const providerService = new ProviderService();

export class MCPService {
    constructor() {
        console.debug('MCPService init');

    }
    token = '';
    baseUrl = '';
    getToken(){
         console.debug('MCPService init token');
        const m = providerService.getMCPConfig();
        this.baseUrl = m.baseUrl;      // e.g. "http://localhost:2500"
        this.token = m.apiKey;        // must match the Python --token
    }
    // parse an /include directive
    parseIncludeBak(text) {
        const parts = text.trim().split(/\s+/).slice(1);
        if (parts.length === 0) return null;
        const cmd = { type: null, file: null, dir: null, pattern: '*', recursive: false };
        if (parts[0] === 'all') {
            cmd.type = 'all';
        } else if (parts[0].startsWith('file=')) {
            cmd.type = 'file';
            cmd.file = parts[0].split('=')[1];
        } else if (parts[0].startsWith('dir=')) {
            cmd.type = 'dir';
            cmd.dir = parts[0].split('=')[1];
            for (let p of parts.slice(1)) {
                if (p.startsWith('pattern=')) cmd.pattern = p.split('=')[1];
                if (p === 'recursive') cmd.recursive = true;
            }
        }
        return cmd;
    }
    parseInclude(text) {
        const parts = text.trim().split(/\s+/).slice(1);
        if (parts.length === 0) return null;
        const cmd = { type: null, file: null, dir: null, pattern: '*', recursive: false };

        const p0 = parts[0];

        if (p0 === 'all') {
            cmd.type = 'all';

        } else if (p0.startsWith('file=')) {
            const spec = p0.slice(5);
            if (/[*?\[]/.test(spec)) {
                // wildcard in file= → search all roots
                cmd.type = 'pattern';
                cmd.pattern = spec;
                cmd.recursive = true;
                cmd.dir = '';       // empty dir→all roots
            } else {
                cmd.type = 'file';
                cmd.file = spec;
            }

        } else if (p0.startsWith('dir=')) {
            cmd.type = 'dir';
            cmd.dir = p0.slice(4);
            for (let p of parts.slice(1)) {
                if (p.startsWith('pattern=')) cmd.pattern = p.slice(8);
                if (p === 'recursive') cmd.recursive = true;
            }
            // if the dir spec itself contains a glob
            if (/[*?\[]/.test(cmd.dir)) {
                cmd.type = 'pattern';
                cmd.pattern = cmd.dir;
                cmd.dir = '';
                cmd.recursive = true;
            }
        }

        // standalone "/include pattern=…"
        else if (p0.startsWith('pattern=')) {
            cmd.type = 'pattern';
            cmd.pattern = p0.slice(8);
            cmd.recursive = true;
            cmd.dir = '';
        }

        return cmd;
    }

    // core callMCP: browser‐fetch or Node net.Socket
    async callMCP(op, payload, timeoutMs = 5000) {
        this.getToken();
        const cmd = `${op} ${JSON.stringify(payload)}\n`;
        // browser path
        if (typeof window !== 'undefined' && typeof fetch === 'function') {
            const controller = new AbortController();
            const id = setTimeout(() => controller.abort(), timeoutMs);

            let resText = ''
            try {
                const res = await fetch(this.baseUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'text/plain',
                        'Authorization': `Bearer ${this.token}`
                    },
                    body: cmd,
                    signal: controller.signal
                });
                clearTimeout(id);
                if (res.status === 401) {
                    throw new Error('MCP Authentication failed (401)');
                }
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`);
                }
                resText = await res.text();
            } catch (e) {
                clearTimeout(id);
                console.error(e)
            }
            const lines = resText.trim().split('\n');
            try {
                return JSON.parse(lines[lines.length - 1]);
            } catch (e) {
                console.error(e)
            }
        }

     
    }

    // one‐line summary for logging
    summarizeResult(obj) {
        try {
            return Object.entries(obj)
                .map(([k, v]) => {
                    if (Array.isArray(v)) return `${k}=[${v.length}]`;
                    if (typeof v === 'string') return `${k}="${v.slice(0, 30)}…"(${v.length})`;
                    if (typeof v === 'object') return `${k}={…}`;
                    return `${k}=${v}`;
                })
                .join(', ');
        } catch {
            return JSON.stringify(obj).slice(0, 100) + '…';
        }
    }
}