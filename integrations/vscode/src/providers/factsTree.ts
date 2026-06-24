import * as vscode from 'vscode';
import { MemoriqMCPClient, Fact } from '../mcp/client';

export class FactTreeItem extends vscode.TreeItem {
    constructor(
        public readonly fact: Fact,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState
    ) {
        super(`[${fact.type}] ${fact.content.substring(0, 40)}...`, collapsibleState);

        this.tooltip = fact.content;
        this.description = fact.timestamp ? new Date(fact.timestamp).toLocaleDateString() : '';

        // Set icon based on type
        switch (fact.type) {
            case 'error_fix':
                this.iconPath = new vscode.ThemeIcon('error');
                break;
            case 'decision':
                this.iconPath = new vscode.ThemeIcon('git-commit');
                break;
            case 'pattern':
                this.iconPath = new vscode.ThemeIcon('symbol-structure');
                break;
            case 'api_contract':
                this.iconPath = new vscode.ThemeIcon('plug');
                break;
            default:
                this.iconPath = new vscode.ThemeIcon('note');
        }

        this.command = {
            command: 'memoriq.openFact',
            title: 'Open Fact',
            arguments: [fact],
        };
    }
}

export class FactsTreeProvider implements vscode.TreeDataProvider<FactTreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<FactTreeItem | undefined | null | void> = new vscode.EventEmitter<FactTreeItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<FactTreeItem | undefined | null | void> = this._onDidChangeTreeData.event;

    private facts: Fact[] = [];

    constructor(private client: MemoriqMCPClient) {
        // Initial load
        this.loadFacts();
    }

    refresh(): void {
        this.loadFacts();
    }

    private async loadFacts(): Promise<void> {
        if (!this.client.isConnected()) {
            return;
        }

        try {
            this.facts = await this.client.listFacts(50);
            this._onDidChangeTreeData.fire();
        } catch (error) {
            console.error('Failed to load facts:', error);
        }
    }

    getTreeItem(element: FactTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: FactTreeItem): Thenable<FactTreeItem[]> {
        if (element) {
            // No children for now
            return Promise.resolve([]);
        }

        // Return root items
        const items = this.facts.map(fact =>
            new FactTreeItem(fact, vscode.TreeItemCollapsibleState.None)
        );

        return Promise.resolve(items);
    }
}
