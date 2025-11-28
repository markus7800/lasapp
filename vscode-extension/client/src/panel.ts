import * as vscode from 'vscode';
import { AnalysisSettings } from './analysisSettings';

export function getWebviewOptions(extensionUri: vscode.Uri): vscode.WebviewOptions {
	return {
		// Enable javascript in the webview
		enableScripts: true,

		// And restrict the webview to only loading content from our extension's `media` directory.
		localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'media')]
	};
}

/**
 * Manages cat coding webview panels
 */
export class CatCodingPanel {
	/**
	 * Track the currently panel. Only allow a single panel to exist at a time.
	 */
	public static currentPanel: CatCodingPanel | undefined;

	public static readonly viewType = 'lasappPanel';

	private readonly _panel: vscode.WebviewPanel;
	private readonly _extensionUri: vscode.Uri;
	private readonly _settings: AnalysisSettings;
	private _onSettingsChanged: (settings: AnalysisSettings) => Promise<void>;

	private _disposables: vscode.Disposable[] = [];

	public static createOrShow(extensionUri: vscode.Uri, settings: AnalysisSettings, onSettingsChanged: (settings: AnalysisSettings) => Promise<void>) {

		// If we already have a panel, show it.
		if (CatCodingPanel.currentPanel) {
			CatCodingPanel.currentPanel._panel.reveal(vscode.ViewColumn.Two);
			return;
		}

		// Otherwise, create a new panel.
		const panel = vscode.window.createWebviewPanel(
			CatCodingPanel.viewType,
			'LASAPP',
			vscode.ViewColumn.Two,
			getWebviewOptions(extensionUri),
		);

		CatCodingPanel.currentPanel = new CatCodingPanel(panel, extensionUri, settings, onSettingsChanged);
	}

	public static revive(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, settings: AnalysisSettings, onSettingsChanged: (settings: AnalysisSettings) => Promise<void>) {
		CatCodingPanel.currentPanel = new CatCodingPanel(panel, extensionUri, settings, onSettingsChanged);
	}

	private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, settings: AnalysisSettings, onSettingsChanged: (settings: AnalysisSettings) => Promise<void>) {
		this._panel = panel;
		this._extensionUri = extensionUri;
		this._settings = settings;
		this._onSettingsChanged = onSettingsChanged;

		// Set the webview's initial html content
		this._update();

		// Listen for when the panel is disposed
		// This happens when the user closes the panel or when the panel is closed programmatically
		this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

		// Update the content based on view changes
		this._panel.onDidChangeViewState(
			() => {
				if (this._panel.visible) {
					this._update();
				}
			},
			null,
			this._disposables
		);

		// Handle messages from the webview
        this._panel.webview.onDidReceiveMessage(
            async (message) => {
                switch (message.command) {
                    case 'requestSettings': {
						console.log("Sending settings:", this._settings);
                        this._panel.webview.postMessage({ command: 'settings', settings: this._settings });
						console.log("Settings requested");
                        return;
                    }
                    case 'toggleSetting': {
                        const setting: string = message.setting;
                        const value: any = message.value;
						console.log(`Setting ${message.setting} updated to ${message.value}`);
						console.log(`Toggling setting ${setting} to ${value}`);
						this._settings[setting as keyof AnalysisSettings] = value;
						console.log("Updated settings:", this._settings);
						await this._onSettingsChanged(this._settings);
                        this._panel.webview.postMessage({ command: 'settings', settings: this._settings });
                        return;
                    }
                }
            },
            null,
            this._disposables
        );
	}

	public doRefactor() {
		// Send a message to the webview webview.
		// You can send any JSON serializable data.
		this._panel.webview.postMessage({ command: 'refactor' });
	}

	public dispose() {
		CatCodingPanel.currentPanel = undefined;

		// Clean up our resources
		this._panel.dispose();

		while (this._disposables.length) {
			const x = this._disposables.pop();
			if (x) {
				x.dispose();
			}
		}
	}

	private _update() {
		const webview = this._panel.webview;

		this._panel.webview.html = this._getHtmlForWebview(webview);
	}


	private _getHtmlForWebview(webview: vscode.Webview) {
		// Local path to main script run in the webview
		const scriptPathOnDisk = vscode.Uri.joinPath(this._extensionUri, 'media', 'main.js');

		// And the uri we use to load this script in the webview
		const scriptUri = webview.asWebviewUri(scriptPathOnDisk);

		// Local path to css styles
		const styleResetPath = vscode.Uri.joinPath(this._extensionUri, 'media', 'reset.css');
		const stylesPathMainPath = vscode.Uri.joinPath(this._extensionUri, 'media', 'vscode.css');

		// Uri to load styles into webview
		const stylesResetUri = webview.asWebviewUri(styleResetPath);
		const stylesMainUri = webview.asWebviewUri(stylesPathMainPath);

		// Use a nonce to only allow specific scripts to be run
		const nonce = getNonce();
		

		return `<!DOCTYPE html>
			<html lang="en">
			<head>
				<meta charset="UTF-8">

				<!--
					Use a content security policy to only allow loading images from https or from our extension directory,
					and only allow scripts that have a specific nonce.
				-->
				<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; img-src ${webview.cspSource} https:; script-src 'nonce-${nonce}';">

				<meta name="viewport" content="width=device-width, initial-scale=1.0">

				<link href="${stylesResetUri}" rel="stylesheet">
				<link href="${stylesMainUri}" rel="stylesheet">

				<title>LASAPP</title>
			</head>
			<body>
				<section id="settings">
                    <h2>Analyses to run</h2>
                    <ul>
                        <li><label><input type="checkbox" id="constraint_verification"/> Verify Constraints</label></li>
                        <li><label><input type="checkbox" id="guide_validation"/> Validate Guide</label></li>
                        <li><label><input type="checkbox" id="hmc_assumptions_checker"/> Check HMC assumptions</label></li>
                    </ul>
                </section>



                <script nonce="${nonce}">
                    const vscode = acquireVsCodeApi();

                    function setCheckbox(id, checked) {
                        const el = document.getElementById(id);
                        if (el) el.checked = !!checked;
                    }

                    window.addEventListener('message', event => {
                        const message = event.data;
                        switch (message.command) {
                            case 'settings': {
                                const s = message.settings;
                                setCheckbox('constraint_verification', s.constraint_verification);
                                setCheckbox('guide_validation', s.guide_validation);
                                setCheckbox('hmc_assumptions_checker', s.hmc_assumptions_checker);
                                break;
                            }
                        }
                    });

                    ['constraint_verification','guide_validation','hmc_assumptions_checker'].forEach(id => {
                        const el = document.getElementById(id);
                        if (el) {
                            el.addEventListener('change', e => {
                                const checked = e.target.checked;
                                vscode.postMessage({ command: 'toggleSetting', setting: id, value: checked });
                            });
                        }
                    });

                    // Request the current settings initially
                    vscode.postMessage({ command: 'requestSettings' });
                </script>
			</body>
			</html>`;
	}
}

function getNonce() {
	let text = '';
	const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
	for (let i = 0; i < 32; i++) {
		text += possible.charAt(Math.floor(Math.random() * possible.length));
	}
	return text;
}
