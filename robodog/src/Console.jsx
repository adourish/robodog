import React, { useState, useEffect } from 'react';
import './Console.css';

import OpenAI from 'openai';

// Function to get the API key from localStorage or prompt the user
function getAPIKey() {
  const storedAPIKey = localStorage.getItem('openaiAPIKey');
  if (storedAPIKey) {
    return storedAPIKey;
  } else {
    const userInput = prompt('Please enter your OpenAI API Key:');
    if (userInput) {
      localStorage.setItem('openaiAPIKey', userInput);
      return userInput;
    } else {
      alert('API Key is required for this application to work.');
      return '';
    }
  }
}

const openai = new OpenAI({
  apiKey: getAPIKey(),
  dangerouslyAllowBrowser: true,
});

// Utility function to send a message to OpenAI
async function sendMessageToOpenAI(text, model, context) {
  const messages = [
    { role: 'system', content: 'You are a helpful assistant.' },
    { role: 'assistant', content: context }, // Include context as a message
    { role: 'user', content: text },
  ];

  const response = await openai.chat.completions.create({
    model: model,
    messages: messages,
  });

  return response;
}

// Function to generate a message with a timestamp
function getMessageWithTimestamp(command, role) {
  const options = { hour12: false, hour: '2-digit', minute: '2-digit' };
  const shortTimeString = new Date().toLocaleTimeString(undefined, options);
  return `${shortTimeString}${role === 'user' ? '👾' : '🤖'}: ${command}`;
}
var model = 'gpt-3.5-turbo-1106';
function Console() {
  const [inputText, setInputText] = useState('');
  const [content, setContent] = useState([]);
  const [context, setContext] = useState('');
  const [isLoading, setIsLoading] = useState(false); // State to track loading status
  const maxChars = 9000;

  const totalChars = context.length + inputText.length;
  const remainingChars = maxChars - totalChars;

  // ...

const handleInputChange = (event) => {
  const value = event.target.value;
  setInputText(value);
};

const handleContextChange = (event) => {
  const value = event.target.value;
  setContext(value);
};

const handleSubmit = async (event) => {
  event.preventDefault();
  const command = inputText.trim();

  if (command.length > remainingChars) {
    // Check if input exceeds character limit and show a message
    setContent([...content, `Input exceeds character limit: ${maxChars} characters allowed.`]);
    return;
  }

  console.log('submit:', command);
  setIsLoading(true); // Set loading status to true

  if (command.startsWith('/')) {
    const commandParts = command.split(' ');
    const cmd = commandParts[0];

    switch (cmd) {
      case '/gpt3':
        model = 'gpt-3.5-turbo-1106';
        const switchMessageGPT3 = `Switching to GPT-3: ${command}`;
        console.log(switchMessageGPT3);
        setContent([
          ...content,
          getMessageWithTimestamp(command, 'user'),
          getMessageWithTimestamp(switchMessageGPT3, 'assistant'),
        ]);
        break;
      case '/gpt4':
        model = 'gpt-4';
        const switchMessageGPT4 = `Switching to GPT-4: ${command}`;
        console.log(switchMessageGPT4);
        setContent([
          ...content,
          getMessageWithTimestamp(command, 'user'),
          getMessageWithTimestamp(switchMessageGPT4, 'assistant'),
        ]);
        break;
      default:
        model = 'gpt-3.5-turbo-1106';
        const switchMessageDefault = `Switching to default (GPT-3.5): ${command}`;
        console.log(switchMessageDefault);
        setContent([
          ...content,
          getMessageWithTimestamp(command, 'user'),
          getMessageWithTimestamp(switchMessageDefault, 'assistant'),
        ]);
    }
  } else {
    console.log('content:', command);
    const response = await sendMessageToOpenAI(command, model, context);
    setContent([
      ...content,
      getMessageWithTimestamp(command, 'user'),
      getMessageWithTimestamp(response.choices[0]?.message?.content, 'assistant'),
    ]);
  }

  setIsLoading(false); // Set loading status to false
  setInputText('');
};

// ...


  const handleNoteCommand = (text) => {
    console.log('Note:', text);
  };

  const handleChatCommand = (text) => {
    const response = sendMessageToOpenAI(text, 'gpt-3.5-turbo', context);
    console.log('Chat:', text);
  };

  const handleTaskCommand = (text) => {
    console.log('Task:', text);
  };

  const handleCalCommand = (text) => {
    console.log('Calendar:', text);
  };

  const handleUnknownCommand = () => {
    console.log('Unknown command');
  };

  return (
    <div className="console">
      <div className="console-content">
        {content.map((text, index) => (
          <pre key={index}>{text}</pre>
        ))}
        {isLoading && <pre>Wait... /</pre>}
      </div>
      <form onSubmit={handleSubmit} className="input-form">
        <div className="char-count">
          {totalChars}/{maxChars} characters remaining
        </div>
        <textarea
          value={context}
          onChange={handleContextChange}
          placeholder="Knowledge (optional)"
          className="input-textarea context-textarea"
        ></textarea>
        <div className="input-area">
          <textarea
            value={inputText}
            onChange={handleInputChange}
            placeholder="Chat"
            className="input-textarea question-textarea"
          ></textarea>
          <button type="submit" className="submit-button">🤖</button>
        </div>
      </form>
    </div>
  );
}

export default Console;
