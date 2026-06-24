import * as vscode from 'vscode';
import { MemoriqMCPClient } from './mcp/client';
import { FactsTreeProvider } from './providers/factsTree';
import { SearchCommand } from './commands/search';
import { WriteCommand } from './commands/write';
import { ContextCommand } from './commands/context';
import { IndexCommand } from './commands/index';

let mcpClient: MemoriqMCPClient | undefined;
let factsProvider: FactsTreeProvider | undefined;

export async function activate(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('memoriq');
    const enabled = config.get<boolean>('enabled', true);

    if (!enabled) {
        console.log('Memoriq is disabled');
        return;
    }

    // Set context for menu visibility
    vscode.commands.executeCommand('setContext', 'memoriq:enabled', true);

    // Initialize MCP client
    mcpClient = new MemoriqMCPClient();

    try {
        await mcpClient.connect();
        vscode.window.showInformationMessage('Memoriq connected');
    } catch (error) {
        vscode.window.showWarningMessage(`Memoriq connection failed: ${error}`);
    }

    // Register tree provider
    factsProvider = new FactsTreeProvider(mcpClient);
    vscode.window.registerTreeDataProvider('memoriq.facts', factsProvider);

    // Register commands
    const searchCmd = new SearchCommand(mcpClient);
    const writeCmd = new WriteCommand(mcpClient);
    const contextCmd = new ContextCommand(mcpClient);
    const indexCmd = new IndexCommand(mcpClient);

    context.subscriptions.push(
        vscode.commands.registerCommand('memoriq.search', () => searchCmd.execute()),
        vscode.commands.registerCommand('memoriq.write', () => writeCmd.execute()),
        vscode.commands.registerCommand('memoriq.context', () => contextCmd.execute()),
        vscode.commands.registerCommand('memoriq.index', () => indexCmd.execute()),
        vscode.commands.registerCommand('memoriq.browse', () => factsProvider?.refresh()),
        vscode.commands.registerCommand('memoriq.refresh', () => factsProvider?.refresh()),
    );

    // Auto-index if enabled
    const autoIndex = config.get<boolean>('autoIndex', false);
    if (autoIndex) {
        await indexCmd.execute();
    }
}

export function deactivate() {
    mcpClient?.disconnect();
}
