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

  try {
    const response = await openai.chat.completions.create({
      model: model,
      messages: messages,
    });

    return response;
  } catch (error) {
    console.error("Error sending message to OpenAI: ", error);
    return null; // return null if there's an error
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
      roleEmoji = '🖥️';
      break;
    default:
      roleEmoji = '';
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
      // Check if input exceeds character limit and show a message
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
          case '/gpt3':
            model = 'gpt-3.5-turbo-1106';
            setMaxChars(10000);
            message = `Switching to GPT-3: gpt-3.5-turbo-1106`;
            break;
          case '/gpt4':
            model = 'gpt-4';
            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4`;
            break;
          case '/help':
            message = 'Available commands: </br>' +
            ' /gpt3 - switch to GPT 3.5 turbo model.' +
            ' /gpt4 - switch to latest GPT 4 model.' +
            ' /help - get help.' +
            ' /reset - Reset your API key';

            break;
          case '/reset':
            localStorage.removeItem('openaiAPIKey');
            window.location.reload(); // Reload the app to prompt the user for API key again
            break;
          default:
            console.log('No verbs.');

        }
        setContent([
          ...content,
          getMessageWithTimestamp(message, 'system')
        ]);
      } else {
        console.log('content:', command);
        const response = await sendMessageToOpenAI(command, model, context, knowledge); // Pass knowledge to the function

        // Append the content of the "Chat" textarea to the "Context" textarea
        const updatedContext = context ? `${context}\n${command}` : command;
        setContext(updatedContext);

        setContent([
          ...content,
          getMessageWithTimestamp(command, 'user'),
          getMessageWithTimestamp(response.choices[0]?.message?.content, 'assistant'),
        ]);
      }
    } catch (ex) {
      console.error('handleSubmit', ex);
      setContent([
        ...content,
        getMessageWithTimestamp(ex, 'system')
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
        {isLoading && <pre>Wait... </pre>}
      </div>
      <form onSubmit={handleSubmit} className="input-form">
        <div className="char-count">
          {totalChars}/{maxChars} characters remaining
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
          placeholder="Knowledge (optional)" // Knowledge input field
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
