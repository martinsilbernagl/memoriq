import * as vscode from 'vscode';
import { MemoriqMCPClient } from '../mcp/client';

export class IndexCommand {
    constructor(private client: MemoriqMCPClient) {}

    async execute(): Promise<void> {
        if (!this.client.isConnected()) {
            vscode.window.showErrorMessage('Memoriq is not connected');
            return;
        }

        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            vscode.window.showErrorMessage('No workspace folder open');
            return;
        }

        const projectPath = workspaceFolders[0].uri.fsPath;

        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Indexing project for Memoriq...',
            cancellable: false,
        }, async (progress) => {
            try {
                const result = await this.client.indexProject(projectPath);
                vscode.window.showInformationMessage(result);
            } catch (error) {
                vscode.window.showErrorMessage(`Indexing failed: ${error}`);
            }
        });
    }
}
