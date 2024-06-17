const vscode = require('vscode');

function activate(context) {
    console.log('Congratulations, your extension "robodog" is now active!');

    const disposable = vscode.commands.registerCommand('extension.openRobodogPanel', function () {
        const panel = vscode.window.createWebviewPanel(
            'robodogPanel',
            'Robodog',
            vscode.ViewColumn.One,
            {}
        );

        panel.webview.html = getWebviewContent();
    });

    context.subscriptions.push(disposable);
}

function getWebviewContent() {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Robodog</title>
</head>
<body>
    <iframe src="https://adourish.github.io/robodog/robodog/dist/" style="width: 100vw; height: 100vh; border: none;"></iframe>
</body>
</html>`;
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
}