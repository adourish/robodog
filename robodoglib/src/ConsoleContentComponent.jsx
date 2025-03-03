
import React from 'react';

function ConsoleContentComponent({ content, handleCopyToClipboard, handleSetModel, handleLaunch }) {

    function stripMarkdown(text) {
        try {
            if (typeof text !== 'string') {
                console.warn('stripMarkdown received non-string input:', text);
                return '';
            }
            return text
                .replace(/\*\*(.*?)\*\*/g, '$1')
                .replace(/\*(.*?)\*/g, '$1')
                .replace(/__(.*?)__/g, '$1')
                .replace(/_(.*?)_/g, '$1')
                .replace(/~~(.*?)~~/g, '$1')
                .replace(/`(.*?)`/g, '$1')
                .replace(/!\[(.*?)\]\((.*?)\)/g, '$1')
                .replace(/\[(.*?)\]\((.*?)\)/g, '$1')
                .replace(/#+\s*(.*)/g, '$1')
                .trim();
        } catch (error) {
            console.error('Error stripping markdown:', error, 'Input text:', text);
            return text;
        }
    }

    const contentItems = [];

    for(let index = 0; index < content.length; index++) {
        const item = content[index];
        if (Array.isArray(item.command)) {
            item.command = String(item.command.join('\n'));
        }
        item.command = stripMarkdown(String(item.command));

        if (item.role === 'image') {
            contentItems.push(
                <div key={index}><img src={item.command} alt={item.role} className='image-size-50' /></div>
            );
        } else if (item.role === 'ufo') {
            contentItems.push(
                <pre className='ufo-text' key={index} focus={item.focus} alt={`${item.datetime}${item.roleEmoji}`}>
                    <code>{item.command}</code>
                </pre>
            );
        } else if (item.role === 'search') {
            contentItems.push(
                <div key={index}>{item.command}<a href={item.url} rel="noreferrer" target="_blank" alt={item.role}>🔗</a></div>
            );
        } else if (item.role === 'popup') {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleLaunch(item.command, item.url)}>
                    <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
                </pre>
            );
        } else if (item.role === 'model') {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleSetModel(item.command)}>
                    <code>{`/model ${item.command}`}</code>
                </pre>
            );
        } else if (item.role === 'setting' || item.role === 'help') {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
                    <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
                </pre>
            );
        } else {
            contentItems.push(
                <pre className='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
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