import React, { useEffect } from 'react';

function ConsoleContentComponent({ content, handleCopyToClipboard, handleSetModel, handleLaunch }) {


    const contentItems = [];

    for(let index = 0; index < content.length; index++) {
        const item = content[index];
        if (Array.isArray(item.command)) {
            item.command = String(item.command.join('\n'));
          }
          item.command = String(item.command);

        //console.trace('console content component', item);
        if (item.role === 'image') {
            contentItems.push(
                <div key="{index}"><img src={item.command} alt={item.role} className='image-size-50' /></div>
            );
        } else if (item.role === 'ufo') {
            contentItems.push(
                <pre class='ufo-text' key={index} focus={item.focus} alt="{item.datetime}{item.roleEmoji}">
                    <code>{item.command}</code>
                </pre>
            );
        } else if (item.role === 'search') {
            contentItems.push(
                <div key="{index}">{`${item.command}`}<a href={item.url} rel="noreferrer" target="_blank" alt={item.role}>🔗</a></div>
            );
        } else if (item.role === 'popup') {
            contentItems.push(
                <pre class='console-text' key={index} focus={item.focus} onClick={() => handleLaunch(item.command, item.url)}>
                    <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
                </pre>
            );
        } else if (item.role === 'model') {
            contentItems.push(
                <pre class='console-text' key={index} focus={item.focus} onClick={() => handleSetModel(item.command)}>
                    <code>{`/model ${item.command}`}</code>
                </pre>
            );
        } else if (item.role === 'setting' || item.role === 'help') {
            contentItems.push(
                <pre class='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
                    <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
                </pre>
            );
        } else {
            contentItems.push(
                <pre class='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
                    <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
                </pre>
            );
        }
    }

    return (
        <div id="consoleContent" className="console-content">
            {contentItems}
        </div>
    );
}

export { ConsoleContentComponent };