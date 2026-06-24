import * as vscode from 'vscode';
import { MemoriqMCPClient } from '../mcp/client';

export class WriteCommand {
    constructor(private client: MemoriqMCPClient) {}

    async execute(): Promise<void> {
        if (!this.client.isConnected()) {
            vscode.window.showErrorMessage('Memoriq is not connected');
            return;
        }

        const content = await vscode.window.showInputBox({
            prompt: 'Write a fact to Memoriq',
            placeHolder: 'Enter fact content...',
        });

        if (!content) {
            return;
        }

        const type = await vscode.window.showQuickPick(
            ['fact', 'decision', 'pattern', 'gotcha', 'api_contract', 'error_fix'],
            {
                placeHolder: 'Select fact type',
            }
        );

        if (!type) {
            return;
        }

        const tags = await vscode.window.showInputBox({
            prompt: 'Tags (optional, comma-separated)',
            placeHolder: 'e.g., api, auth, frontend',
        });

        try {
            const result = await this.client.write(content, type, tags);
            vscode.window.showInformationMessage(result);
        } catch (error) {
            vscode.window.showErrorMessage(`Write failed: ${error}`);
        }
    }
}
