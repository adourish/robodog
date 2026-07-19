
import React from 'react';

function ConsoleContentComponent({ content, handleCopyToClipboard, handleSetModel, handleLaunch }) {

    const contentItems = [];

    for(let index = 0; index < content.length; index++) {
        const item = content[index];
        if (Array.isArray(item.command)) {
            item.command = String(item.command.join('\n'));
        }
        if (item.role === 'image') {
            contentItems.push(
                <div key={index}><img src={item.command} alt={item.role} className='image-size-50' /></div>
            );
        } else if (item.role === 'ufo') {
            contentItems.push(
                <pre className='ufo-text' key={index} focus={item.focus} alt={`${item.datetime}${item.roleEmoji}`}>
                    {item.command}
                </pre>
            );
        } else if (item.role === 'search') {
            contentItems.push(
                <div key={index}>{item.command}<a href={item.url} rel="noreferrer" target="_blank" alt={item.role}>🔗</a></div>
            );
        } else if (item.role === 'popup') {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleLaunch(item.command, item.url)}>
                    {`${item.datetime} ${item.roleEmoji}:${item.command}`}
                </pre>
            );
        } else if (item.role === 'user') {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
{`${item.datetime} ${item.roleEmoji}:${item.command}`}
                </pre>
            );
        } else if (item.role === 'assistant') {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
{`${item.datetime} ${item.roleEmoji}:
${item.command}`}
                </pre>
            );
        } else if (item.role === 'setting' || item.role === 'help') {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
                    {`${item.datetime} ${item.roleEmoji}:${item.command}`}
                </pre>
            );
        } else {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
{`${item.datetime} ${item.roleEmoji}:
${item.command}`}
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