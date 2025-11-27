/* --------------------------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See License.txt in the project root for license information.
 * ------------------------------------------------------------------------------------------ */

import * as path from 'path';
import { workspace, ExtensionContext } from 'vscode';
import { exec, spawn, spawnSync } from 'node:child_process';
import * as fs from "fs";
import * as vscode from 'vscode';

import {
	LanguageClient,
	LanguageClientOptions,
	ServerOptions,
	TransportKind
} from 'vscode-languageclient/node';

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

export async function activate(context: ExtensionContext) {
	console.log("Activate Client.")


	const lasappPython = await vscode.window.withProgress(
		{ location: vscode.ProgressLocation.Window, title: "Preparing Lasapp server..." },
		async () => {
			return await ensureVenv(context.asAbsolutePath(path.join('lasapp', 'src')));
		}
	);

	console.log(lasappPython)

	context.extensionPath
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
			analysisPython: lasappPython,
			analysisFile: context.asAbsolutePath(path.join("server", "src", "test.py")),
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
}

export function deactivate(): Thenable<void> | undefined {
	if (!client) {
		return undefined;
	}
	return client.stop();
}
