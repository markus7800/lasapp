/* --------------------------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License. See License.txt in the project root for license information.
 * ------------------------------------------------------------------------------------------ */
import {
	createConnection,
	TextDocuments,
	Diagnostic,
	DiagnosticSeverity,
	ProposedFeatures,
	InitializeParams,
	DidChangeConfigurationNotification,
	CompletionItem,
	CompletionItemKind,
	TextDocumentPositionParams,
	TextDocumentSyncKind,
	InitializeResult,
	DocumentDiagnosticReportKind,
	type DocumentDiagnosticReport,
	Position
} from 'vscode-languageserver/node';
import { exec, spawn } from 'node:child_process';

import {
	TextDocument
} from 'vscode-languageserver-textdocument';
import { AnalysisSettings } from './analysisSettings'; // TODO: find a way to share this class definition between client and server

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


// Create a connection for the server, using Node's IPC as a transport.
// Also include all preview / proposed LSP features.
const connection = createConnection(ProposedFeatures.all);

// Create a simple text document manager.
const documents = new TextDocuments(TextDocument);

let hasConfigurationCapability = false;
let hasWorkspaceFolderCapability = false;
let hasDiagnosticRelatedInformationCapability = false;

let analysisPython = "";
let analysisFile = "";
let analysisWd = "";
let analysisSettings: AnalysisSettings;

connection.onInitialize((params: InitializeParams) => {
	// console.log("Server onInitialize", params)
	const capabilities = params.capabilities;
	analysisPython = params.initializationOptions?.analysisPython;
	analysisFile = params.initializationOptions?.analysisFile;
	analysisWd = params.initializationOptions?.analysisWd;
	analysisSettings = params.initializationOptions?.analysisSettings;

	// Does the client support the `workspace/configuration` request?
	// If not, we fall back using global settings.
	hasConfigurationCapability = !!(
		capabilities.workspace && !!capabilities.workspace.configuration
	);
	hasWorkspaceFolderCapability = !!(
		capabilities.workspace && !!capabilities.workspace.workspaceFolders
	);
	hasDiagnosticRelatedInformationCapability = !!(
		capabilities.textDocument &&
		capabilities.textDocument.publishDiagnostics &&
		capabilities.textDocument.publishDiagnostics.relatedInformation
	);

	const result: InitializeResult = {
		capabilities: {
			textDocumentSync: TextDocumentSyncKind.Incremental,
			diagnosticProvider: {
				interFileDependencies: false,
				workspaceDiagnostics: false
			}
		}
	};
	if (hasWorkspaceFolderCapability) {
		result.capabilities.workspace = {
			workspaceFolders: {
				supported: true
			}
		};
	}
	return result;
});

connection.onInitialized(() => {
	if (hasConfigurationCapability) {
		// Register for all configuration changes.
		connection.client.register(DidChangeConfigurationNotification.type, undefined);
	}
	if (hasWorkspaceFolderCapability) {
		connection.workspace.onDidChangeWorkspaceFolders(_event => {
			connection.console.log('Workspace folder change event received.');
		});
	}

	connection.onNotification('analysisSettings', (settings: any) => {
		try {
			// Replace existing settings object with incoming settings object
			analysisSettings = settings as AnalysisSettings;
			console.log('Server: received analysisSettings update: ' + JSON.stringify(settings));
		} catch (err) {
			console.error('Failed to update analysisSettings: ' + (err as Error).message);
		}
	});
});


// The example settings
interface ExampleSettings {
	maxNumberOfProblems: number;
}

// The global settings, used when the `workspace/configuration` request is not supported by the client.
// Please note that this is not the case when using this server with the client provided in this example
// but could happen with other clients.
const defaultSettings: ExampleSettings = { maxNumberOfProblems: 1000 };
let globalSettings: ExampleSettings = defaultSettings;

// Cache the settings of all open documents
const documentSettings = new Map<string, Thenable<ExampleSettings>>();

connection.onDidChangeConfiguration(change => {
	if (hasConfigurationCapability) {
		// Reset all cached document settings
		documentSettings.clear();
	} else {
		globalSettings = (
			(change.settings.languageServerExample || defaultSettings)
		);
	}
	// Refresh the diagnostics since the `maxNumberOfProblems` could have changed.
	// We could optimize things here and re-fetch the setting first can compare it
	// to the existing setting, but this is out of scope for this example.
	connection.languages.diagnostics.refresh();
});

function getDocumentSettings(resource: string): Thenable<ExampleSettings> {
	if (!hasConfigurationCapability) {
		return Promise.resolve(globalSettings);
	}
	let result = documentSettings.get(resource);
	if (!result) {
		result = connection.workspace.getConfiguration({
			scopeUri: resource,
			section: 'languageServerExample'
		});
		documentSettings.set(resource, result);
	}
	return result;
}

// Only keep settings for open documents
documents.onDidClose(e => {
	documentSettings.delete(e.document.uri);
});


connection.languages.diagnostics.on(async (params) => {
	const document = documents.get(params.textDocument.uri);
	if (document !== undefined) {
		return {
			kind: DocumentDiagnosticReportKind.Full,
			items: []
		} satisfies DocumentDiagnosticReport;
	} else {
		// We don't know the document. We can either try to read it from disk
		// or we don't report problems for it.
		return {
			kind: DocumentDiagnosticReportKind.Full,
			items: []
		} satisfies DocumentDiagnosticReport;
	}
});

// The content of a text document has changed. This event is emitted
// when the text document first opened or when its content has changed.
documents.onDidChangeContent(change => {
});

documents.onDidSave(async (e) => {
	const diagnostics = await validateTextDocument(e.document);
	connection.sendDiagnostics({ uri: e.document.uri, diagnostics: diagnostics });
});


function runPythonAnalysis(source: string): Promise<any[]> {
    return new Promise((resolve, reject) => {
		try {
			let args = [analysisFile];
			if (analysisSettings.constraint_verification) {
				args.push("--constraint");
			}
			if (analysisSettings.guide_validation) {
				args.push("--guide");
			}
			if (analysisSettings.hmc_assumptions_checker) {
				args.push("--hmc");
			}
			if (analysisSettings.funnel_detection) {
				args.push("--funnel");
			}
			console.log("Running analysis:", args.join(" "), "in", analysisWd)
			const py = spawn(analysisPython, args, {cwd: analysisWd});

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

			py.stdin.write(source);
			py.stdin.end();
		} catch (error) {
			reject(error)
		}
        
    });
}


async function validateTextDocument(textDocument: TextDocument): Promise<Diagnostic[]> {
	// In this simple example we get the settings for every validate run.
	console.log("validate", textDocument.uri)
	const diagnostics: Diagnostic[] = [];

	const text = textDocument.getText();
	const result = await runPythonAnalysis(text);

	result.forEach(violation => {
		// console.log(violation)
		const diagnostic: Diagnostic = {
			severity: DiagnosticSeverity.Warning,
			range: {
				start: textDocument.positionAt(violation.start_index),
				end: textDocument.positionAt(violation.end_index),
			},
			message: violation.description,
			source: 'lasapp'
		};
		diagnostics.push(diagnostic);
	});
	return diagnostics;
}

connection.onDidChangeWatchedFiles(_change => {
	// Monitored files have change in VSCode
	connection.console.log('We received a file change event');
});

// Make the text document manager listen on the connection
// for open, change and close text document events
documents.listen(connection);

// Listen on the connection
connection.listen();
