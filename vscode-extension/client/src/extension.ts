/* --------------------------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See License.txt in the project root for license information.
 * ------------------------------------------------------------------------------------------ */

import * as path from 'path';
import { workspace, ExtensionContext } from 'vscode';
import { exec, spawn, spawnSync } from 'node:child_process';
import { CatCodingPanel, getWebviewOptions } from './panel';
import { AnalysisSettings } from './analysisSettings';
import * as fs from "fs";
import * as vscode from 'vscode';

import {
	LanguageClient,
	LanguageClientOptions,
	ServerOptions,
	TransportKind
} from 'vscode-languageclient/node';
import { stdout } from 'node:process';

function run(cmd: string, cwd: string): Promise<string> {
    return new Promise((resolve, reject) => {
        exec(cmd, { cwd }, (err, stdout, stderr) => {
            // if (stdout) console.log(stdout);
            // if (stderr) console.error(stderr);
            if (err) reject(err);
            else resolve(stdout);
        });
    });
}

async function ensureVenv(pythonDir: string): Promise<string> {
    const venvPath = path.join(pythonDir, "venv");

	const pythonPath = process.platform === "win32"
        ? path.join(venvPath, "Scripts", "python.exe")
        : path.join(venvPath, "bin", "python");

    if (!fs.existsSync(venvPath)) {
        console.log("Creating Python venv...");
        await run("python3 -m venv venv", pythonDir);
    } else {
		console.log("Found venv at " + venvPath);
	}

	const requirements = path.join(pythonDir, "py-requirements.txt");
	if (fs.existsSync(requirements)) {
		const packageList = await run(pythonPath + " -m pip freeze", pythonDir);
		if (!packageList.includes("ast_scope")){
			console.log("Installing requirements...");
			await run(pythonPath + " -m pip install -r py-requirements.txt", pythonDir);
		} else {
			console.log("Requirements already installed.");
		}
	}

    return pythonPath
}

let client: LanguageClient;
let analysisSettings = new AnalysisSettings();

function sendAnalysisSettingsToServer(settings: AnalysisSettings) {
    if (!client) return;
    try {
        const payload = JSON.parse(JSON.stringify(settings)); // ensure plain object (no methods)
		console.log("Client: Sending analysisSettings to server:", payload);
        client.sendNotification('analysisSettings', payload);
    } catch (err) {
        console.error('Error sending analysisSettings to server:', err);
    }
}

function get_model_graph(context: ExtensionContext, analysisPython: string, document: vscode.TextDocument) :Promise<any> {
	let analysisWd = context.asAbsolutePath(".");
	let analysisFile = context.asAbsolutePath(path.join("client", "src", "graph.py"));
	return new Promise((resolve, reject) => {
		const py = spawn(analysisPython, [analysisFile], {cwd: analysisWd});

		let stdout = "";
		let stderr = "";

		py.stdout.on("data", (data) => {
			stdout += data.toString();
		});

		py.stderr.on("data", (data) => {
			stderr += data.toString();
		});

		py.on("close", (code) => {
			if (code !== 0) {
				return reject(new Error("Python error: " + stderr));
			}
			try {
				resolve(JSON.parse(stdout));
			} catch (err) {
				reject(err);
			}
		});

		py.stdin.write(document.getText());
		py.stdin.end();
	})
}

export async function activate(context: ExtensionContext) {
	console.log("Activate Client.")


	const lasappPython = await vscode.window.withProgress(
		{ location: vscode.ProgressLocation.Window, title: "Preparing Lasapp server..." },
		async () => {
			return await ensureVenv(context.asAbsolutePath(path.join('lasapp', 'src')));
		}
	);

	console.log(lasappPython)

	const lasappPyServer = spawn(lasappPython, ["lasapp/src/py/server_pipe.py"], {
		cwd: context.asAbsolutePath("."),
        stdio: ["pipe", "pipe", "pipe"]
	})
	console.log("Spawned lasappPyServer")
	// console.log(await run("ls -a", context.asAbsolutePath(".")));

    context.subscriptions.push({
        dispose() {
			console.log("Kill lasappPyServer")
            lasappPyServer.kill();
        }
    });

	// const res = await run(`${lasappPython} ${context.asAbsolutePath(path.join("server", "src", "test.py"))} ${context.asAbsolutePath(path.join("test_programs", "linear_regression.py"))}`, context.asAbsolutePath("."));
	// console.log("here", res)


	const serverModule = context.asAbsolutePath(
		path.join('server', 'out', 'server.js')
	);


	// If the extension is launched in debug mode then the debug server options are used
	// Otherwise the run options are used
	const serverOptions: ServerOptions = {
		run: { module: serverModule, transport: TransportKind.ipc },
		debug: {
			module: serverModule,
			transport: TransportKind.ipc,
		}
	};

	// Options to control the language client
	const clientOptions: LanguageClientOptions = {
		// Register the server for plain text documents
		documentSelector: [{ scheme: 'file', language: 'python' }],
		initializationOptions: {
			analysisSettings: analysisSettings,
			analysisPython: lasappPython,
			analysisFile: context.asAbsolutePath(path.join("server", "src", "analyse.py")),
			analysisWd: context.asAbsolutePath(".")
		},
		synchronize: {
			// Notify the server about file changes to '.clientrc files contained in the workspace
			fileEvents: workspace.createFileSystemWatcher('**/.clientrc')
		}
	};

	// Create the language client and start the client.
	client = new LanguageClient(
		'lasapp',
		'LASAPP',
		serverOptions,
		clientOptions
	);

	// Start the client. This will also launch the server
	client.start();

	let onSettingsChanged = (async (newSettings: AnalysisSettings) => {
		console.log("Client: Settings changed", newSettings);
		analysisSettings = newSettings;
		sendAnalysisSettingsToServer(newSettings);
	});

    context.subscriptions.push(
        workspace.onDidSaveTextDocument((document: vscode.TextDocument) => {
            if (document.languageId === 'python') {
                CatCodingPanel.createOrShow(context.extensionUri, analysisSettings, onSettingsChanged);
				get_model_graph(context, lasappPython, document).then((result) => {
					CatCodingPanel.currentPanel?.updateModel(document, result["svg"], result["rv_positions"]);
				})
			}
        })
    );

	if (vscode.window.registerWebviewPanelSerializer) {
		// Make sure we register a serializer in activation event
		vscode.window.registerWebviewPanelSerializer(CatCodingPanel.viewType, {
			async deserializeWebviewPanel(webviewPanel: vscode.WebviewPanel, state: unknown) {
				console.log(`Got state: ${state}`);
				// Reset the webview options so we use latest uri for `localResourceRoots`.
				webviewPanel.webview.options = getWebviewOptions(context.extensionUri);
				CatCodingPanel.revive(webviewPanel, context.extensionUri, analysisSettings, onSettingsChanged);
			}
		});
	}
}

export function deactivate(): Thenable<void> | undefined {
	if (!client) {
		return undefined;
	}
	return client.stop();
}
