import React from 'react';

function ConsoleContentComponent({ content, handleCopyToClipboard, handleSetModel, handleLaunch }) {
    return (
        <div id="consoleContent" className="console-content">
            {content.map((item, index) => {
                if (item.role === 'image') {
                    return (
                        <div key="{index}"><img src={item.command} alt={item.role} className='image-size-50' /></div>
                    );
                } else if (item.role === 'ufo') {
                    return (
                        <pre class='ufo-text' key={index} focus={item.focus} alt="{item.datetime}{item.roleEmoji}">
                            <code>{item.command}</code>
                        </pre>
                    );
                } else if (item.role === 'search') {
                    return (
                        <div key="{index}">{`${item.command}`}<a href={item.url} rel="noreferrer" target="_blank" alt={item.role}>🔗</a></div>
                    );
                } else if (item.role === 'popup') {
                    return (
                        <pre class='console-text' key={index} focus={item.focus} onClick={() => handleLaunch(item.command, item.url)}>
                            <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
                        </pre>
                    );
                } else if (item.role === 'model') {
                    return (
                        <pre class='console-text' key={index} focus={item.focus} onClick={() => handleSetModel(item.command)}>
                            <code>{`/model ${item.command}`}</code>
                        </pre>
                    );
                } else if (item.role === 'setting' || item.role === 'help') {
                    return (
                        <pre class='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
                            <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
                        </pre>
                    );
                } else {
                    return (
                        <pre class='console-text' key={index} focus={item.focus} onClick={() => handleCopyToClipboard(item.command)}>
                            <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
                        </pre>
                    );
                }
            })}
        </div>
    );
}

export { ConsoleContentComponent };