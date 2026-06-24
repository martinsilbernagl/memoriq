import * as vscode from 'vscode';
import { MemoriqMCPClient } from '../mcp/client';

export class ContextCommand {
    constructor(private client: MemoriqMCPClient) {}

    async execute(): Promise<void> {
        if (!this.client.isConnected()) {
            vscode.window.showErrorMessage('Memoriq is not connected');
            return;
        }

        // Get the current selection or word under cursor
        const editor = vscode.window.activeTextEditor;
        let symbol = '';

        if (editor) {
            const selection = editor.selection;
            if (!selection.isEmpty) {
                symbol = editor.document.getText(selection);
            } else {
                // Get word under cursor
                const range = editor.document.getWordRangeAtPosition(selection.active);
                if (range) {
                    symbol = editor.document.getText(range);
                }
            }
        }

        const input = await vscode.window.showInputBox({
            prompt: 'Show context for symbol',
            placeHolder: 'Enter function or class name...',
            value: symbol,
        });

        if (!input) {
            return;
        }

        try {
            const result = await this.client.getContext(input);

            // Format and display the result
            const content = JSON.stringify(result, null, 2);
            const doc = await vscode.workspace.openTextDocument({
                content,
                language: 'json',
            });

            await vscode.window.showTextDocument(doc, {
                viewColumn: vscode.ViewColumn.Beside,
            });
        } catch (error) {
            vscode.window.showErrorMessage(`Context lookup failed: ${error}`);
        }
    }
}
