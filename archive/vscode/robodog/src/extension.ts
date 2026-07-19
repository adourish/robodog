/*---------------------------------------------------------
 * Copyright (C) Microsoft Corporation. All rights reserved.
 *--------------------------------------------------------*/


import * as vscode from 'vscode';
import { add } from './robodogService';

export function activate(context: vscode.ExtensionContext) {

	const disposable = vscode.commands.registerCommand('extension.robdog', () => {
		vscode.window.showInformationMessage(`robdog`);
	});

	context.subscriptions.push(disposable);
}
