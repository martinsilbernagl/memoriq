import * as vscode from 'vscode';
import { MemoriqMCPClient } from '../mcp/client';

export class SearchCommand {
    constructor(private client: MemoriqMCPClient) {}

    async execute(): Promise<void> {
        if (!this.client.isConnected()) {
            vscode.window.showErrorMessage('Memoriq is not connected');
            return;
        }

        const query = await vscode.window.showInputBox({
            prompt: 'Search Memoriq memory',
            placeHolder: 'Enter search query...',
        });

        if (!query) {
            return;
        }

        try {
            const results = await this.client.search(query, 10);

            if (results.length === 0) {
                vscode.window.showInformationMessage('No results found');
                return;
            }

            const items = results.map(r => ({
                label: `[${r.type}] ${r.content.substring(0, 60)}...`,
                description: r.content.substring(0, 100),
                detail: `Score: ${r.score.toFixed(2)}`,
            }));

            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: 'Select a result to view',
            });

            if (selected) {
                // Show full content in a new document
                const doc = await vscode.workspace.openTextDocument({
                    content: selected.description,
                    language: 'markdown',
                });
                await vscode.window.showTextDocument(doc);
            }
        } catch (error) {
            vscode.window.showErrorMessage(`Search failed: ${error}`);
        }
    }
}
