import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import * as vscode from 'vscode';
import * as path from 'path';
import * as os from 'os';

export interface Fact {
    id: string;
    content: string;
    type: string;
    tags?: string;
    timestamp?: string;
    project?: string;
}

export interface SearchResult {
    id: string;
    content: string;
    type: string;
    score: number;
}

export class MemoriqMCPClient {
    private client: Client | undefined;
    private transport: StdioClientTransport | undefined;
    private connected: boolean = false;

    async connect(): Promise<void> {
        const config = vscode.workspace.getConfiguration('memoriq');
        const serverPath = config.get<string>('serverPath', '~/.memoriq/mcp-server/server.py');
        const pythonPath = config.get<string>('pythonPath', 'python');

        // Expand home directory
        const expandedPath = serverPath.replace(/^~/, os.homedir());

        this.client = new Client({
            name: 'vscode-memoriq',
            version: '1.0.0',
        });

        this.transport = new StdioClientTransport({
            command: pythonPath,
            args: [expandedPath],
        });

        await this.client.connect(this.transport);
        this.connected = true;
    }

    disconnect(): void {
        this.transport?.close();
        this.connected = false;
    }

    isConnected(): boolean {
        return this.connected;
    }

    async search(query: string, limit: number = 5): Promise<SearchResult[]> {
        if (!this.client || !this.connected) {
            throw new Error('Not connected to Memoriq');
        }

        const result = await this.client.callTool({
            name: 'memory_search',
            arguments: { query, limit },
        });

        // Parse result content
        const content = result.content as Array<{ type: string; text: string }>;
        const text = content.find(c => c.type === 'text')?.text || '';

        // Parse the text output (simplified parsing)
        return this.parseSearchResults(text);
    }

    async write(content: string, type: string = 'fact', tags?: string): Promise<string> {
        if (!this.client || !this.connected) {
            throw new Error('Not connected to Memoriq');
        }

        const result = await this.client.callTool({
            name: 'memory_write',
            arguments: { content, type, tags },
        });

        const resultContent = result.content as Array<{ type: string; text: string }>;
        return resultContent.find(c => c.type === 'text')?.text || 'Unknown result';
    }

    async getContext(symbol: string): Promise<any> {
        if (!this.client || !this.connected) {
            throw new Error('Not connected to Memoriq');
        }

        const result = await this.client.callTool({
            name: 'code_context',
            arguments: { symbol },
        });

        return result;
    }

    async indexProject(projectPath: string): Promise<string> {
        if (!this.client || !this.connected) {
            throw new Error('Not connected to Memoriq');
        }

        const result = await this.client.callTool({
            name: 'code_index',
            arguments: { project_path: projectPath },
        });

        const content = result.content as Array<{ type: string; text: string }>;
        return content.find(c => c.type === 'text')?.text || 'Indexing complete';
    }

    async listFacts(limit: number = 50): Promise<Fact[]> {
        if (!this.client || !this.connected) {
            return [];
        }

        try {
            const result = await this.client.callTool({
                name: 'memory_search',
                arguments: { query: '*', limit },
            });

            const content = result.content as Array<{ type: string; text: string }>;
            const text = content.find(c => c.type === 'text')?.text || '';

            return this.parseFacts(text);
        } catch (error) {
            console.error('Failed to list facts:', error);
            return [];
        }
    }

    private parseSearchResults(text: string): SearchResult[] {
        // Simplified parsing - would need to match actual output format
        const results: SearchResult[] = [];
        const lines = text.split('\n');

        for (const line of lines) {
            // Look for result patterns like "1. [fact] content..."
            const match = line.match(/^\d+\.\s*\[([^\]]+)\]\s*(.+)/);
            if (match) {
                results.push({
                    id: '',
                    type: match[1],
                    content: match[2],
                    score: 0,
                });
            }
        }

        return results;
    }

    private parseFacts(text: string): Fact[] {
        // Simplified parsing
        const facts: Fact[] = [];
        const lines = text.split('\n');

        for (const line of lines) {
            const match = line.match(/^\d+\.\s*\[([^\]]+)\]\s*(.+)/);
            if (match) {
                facts.push({
                    id: '',
                    type: match[1],
                    content: match[2],
                });
            }
        }

        return facts;
    }
}
