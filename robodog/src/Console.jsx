import React, { useState } from 'react';
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

async function sendMessageToOpenAI(text, model, context, knowledge) {
  const messages = [
    { role: 'assistant', content: 'context:' + context },
    { role: 'assistant', content: 'knowledge:' + knowledge }, // Include context as a message
    { role: 'user', content: 'chat: ' + text }
  ];
  console.log('sendMessageToOpenAI:', model, context, knowledge, text);
  try {

    const response = await openai.chat.completions.create({
      model: model,
      messages: messages,
    });
    console.log(response);
    return response;
  } catch (error) {
    console.error("Error sending message to OpenAI: ", error);
    throw error;
  
    return null; 
  }
}

// Function to generate a message with a timestamp
function getMessageWithTimestamp(command, role) {
  const options = { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' };
  const shortTimeString = new Date().toLocaleTimeString(undefined, options);

  let roleEmoji;
  switch (role) {
    case 'user':
      roleEmoji = '👾';
      break;
    case 'assistant':
      roleEmoji = '🤖';
      break;
    case 'system':
      roleEmoji = '💾';
      break;
    case 'error':
      roleEmoji = '💩';
      break;
    default:
      roleEmoji = '🍄';
  }
  return `${shortTimeString}${roleEmoji}: ${command}`;
}

var model = 'gpt-3.5-turbo-1106';

function Console() {
  const [maxChars, setMaxChars] = useState(9000);
  const [inputText, setInputText] = useState('');
  const [content, setContent] = useState([]);
  const [context, setContext] = useState('');
  const [knowledge, setKnowledge] = useState(''); // State for knowledge input
  const [isLoading, setIsLoading] = useState(false); // State to track loading status


  const totalChars = context.length + inputText.length + knowledge.length; // Include knowledge length
  const remainingChars = maxChars - totalChars;

  const handleInputChange = (event) => {
    const value = event.target.value;
    setInputText(value);
  };

  const handleContextChange = (event) => {
    const value = event.target.value;
    setContext(value);
  };

  const handleKnowledgeChange = (event) => {
    const value = event.target.value;
    setKnowledge(value);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const command = inputText.trim();
    var message = '';

    if (command.length > remainingChars) {
      setContent([...content, `Input exceeds character limit: ${maxChars} characters allowed.`]);
      return;
    }

    console.log('submit:', command);
    setIsLoading(true); // Set loading status to true
    try {
      if (command.startsWith('/')) {
        const commandParts = command.split(' ');
        const cmd = commandParts[0];

        switch (cmd) {
          case '/clear':
            setContext('');
            setKnowledge('');
            setContent('');
            break;
          case '/gpt-3.5-turbo-16k':
            model = 'gpt-3.5-turbo-16k';
            setMaxChars(20000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo-16k`;
            break;
          case '/gpt-3.5-turbo-1106':
            model = 'gpt-3.5-turbo-1106';
            setMaxChars(10000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo-1106`;
            break;
          case '/gpt-3.5-turbo':
            model = 'gpt-3.5-turbo';
            setMaxChars(10000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo`;
            break;
          case '/gpt-4':
            model = 'gpt-4';
            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4`;
            break;
          case '/gpt-4-1106-preview':
            model = '/gpt-4-1106-preview';
            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4-1106-preview`;
            break;
          case '/help':
            message = 'Available commands: ' +
              ' /gpt-3.5-turbo - switch to gpt-3.5-turbo-1106 model (4,096 tokens).' +
              ' /gpt-3.5-turbo-16k - switch to gpt-3.5-turbo-16k model (16,385 tokens).' +
              ' /gpt-3.5-turbo-1106 - switch to gpt-3.5-turbo-1106 model (16,385 tokens).' +
              ' /gpt-4 - switch to gpt-4 model (8,192 tokens).' +
              ' /gpt-4-1106-preview - switch to gpt-4-1106-preview model (128,000 tokens).' +
              ' /help - get help.' +
              ' /clear - clear text boxes.' +
              ' /reset - Reset your API key';

            break;
          case '/reset':
            localStorage.removeItem('openaiAPIKey');
            window.location.reload(); // Reload the app to prompt the user for API key again
            break;
          default:
            message = '🍄';
            console.log('No verbs.');

        }
        setContent([
          ...content,
          getMessageWithTimestamp(message, 'system')
        ]);
      } else {
        console.log('content:', command);
        const response = await sendMessageToOpenAI(command, model, context, knowledge); // Pass knowledge to the function
        if (response) {
          // Append the content of the "Chat" textarea to the "Context" textarea
          const updatedContext = context ? `${context}\n${command}` : command;
          setContext(updatedContext);

          setContent([
            ...content,
            getMessageWithTimestamp(command, 'user'),
            getMessageWithTimestamp(response.choices[0]?.message?.content, 'assistant'),
          ]);
        }
      }
    } catch (ex) {
      console.error('handleSubmit', ex);
      setContent([
        ...content,
        getMessageWithTimestamp(ex, 'error')
      ]);
    } finally {
      setIsLoading(false); // Set loading status to false
      setInputText('');
    }
  };

  return (
    <div className="console">
      <div className="console-content">
        {content.map((text, index) => (
          <pre key={index}>{text}</pre>
        ))}
        {isLoading && <pre>⏳</pre>}
      </div>
      <form onSubmit={handleSubmit} className="input-form">
        <div className="char-count">
          {totalChars}/{maxChars}
        </div>
        <textarea
          value={context}
          onChange={handleContextChange}
          placeholder="Context (optional)"
          className="input-textarea context-textarea"
        ></textarea>
        <textarea
          value={knowledge}
          onChange={handleKnowledgeChange}
          placeholder="Knowledge (optional)"
          className="input-textarea knowledge-textarea"
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
