
import { FormatService } from './FormatService';
import { ConsoleService } from './ConsoleService';
import { ProviderService } from './ProviderService';
const formatService = new FormatService();
const consoleService = new ConsoleService();
const providerService = new ProviderService();
const MCP_SERVER_URL = 'http://localhost:2500';
export class MCPService {
    constructor() {
        console.debug('MCPService init');
        this.console = new ConsoleService();
    }

    // parse an /include directive
    parseInclude(text) {
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

    // core callMCP: browser‐fetch or Node net.Socket
    async callMCP(op, payload, timeoutMs = 5000) {
        const cmd = `${op} ${JSON.stringify(payload)}\n`;
        // browser path
        if (typeof window !== 'undefined' && typeof fetch === 'function') {
            const controller = new AbortController();
            const id = setTimeout(() => controller.abort(), timeoutMs);
            let text;
            try {
                const res = await fetch(MCP_SERVER_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'text/plain' },
                    body: cmd,
                    signal: controller.signal
                });
                clearTimeout(id);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                text = await res.text();
            } catch (err) {
                clearTimeout(id);
                throw err;
            }
            const lines = text.trim().split('\n');
            try {
                return JSON.parse(lines[lines.length - 1]);
            } catch (e) {
                throw new Error('Failed to parse MCP JSON: ' + e.message);
            }
        }

        // Node.js path
        let netLib;
        try { netLib = require('net'); } catch (_) { throw new Error("TCP/net unsupported"); }
        return new Promise((resolve, reject) => {
            const client = new netLib.Socket();
            let buffer = '';
            client.setTimeout(timeoutMs, () => {    
                client.destroy();
                reject(new Error('MCP call timed out'));
            });
            client.connect(2500, '127.0.0.1', () => client.write(cmd));
            client.on('data', d => buffer += d.toString('utf8'));
            client.on('end', () => {
                const lines = buffer.trim().split('\n');
                try { resolve(JSON.parse(lines[lines.length - 1])); }
                catch (e) { reject(new Error('Failed to parse MCP JSON: ' + e.message)); }
            });
            client.on('error', reject);
        });
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