import './Console.css';
import OpenAI from 'openai';
import React, { useRef, useEffect, useState } from 'react';

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

async function sendMessageToOpenAI(text, model, context, knowledge, completionType, setContent, setContext, content, setTokens) {
  const _messages = [
    { role: "user", content: "chat history:" + context },
    { role: "user", content: "my knowledge:" + knowledge  },
    { role: "user", content: "question: " + text  }
  ];
  var _content = '';
  var _c = '';

  try {
    let response;

    if (completionType === 'rest') {
      response = await openai.chat.completions.create({
        model: model,
        messages: _messages,
      });
      if (response) {
        _content = response.choices[0]?.message?.content;
        setContent([
          ...content,
          getMessageWithTimestamp(text, 'user'),
          getMessageWithTimestamp(_content, 'assistant')
        ]);
        var _tokens = response.usage?.completion_tokens + '+' + response.usage?.prompt_tokens + '=' + response.usage?.total_tokens;
        setTokens(_tokens)
      }
    }
    else if (completionType === 'stream') {
      const stream = await openai.chat.completions.create({
        model: model,
        messages: _messages,
        stream: true,
      });
      if (stream) {

        for await (const chunk of stream) {
          var _d = chunk.choices[0]?.delta;
          var _temp = chunk.choices[0]?.delta?.content || '';     
          _c = _c + _temp;
          setContent([
            ...content,
            getMessageWithTimestamp(text, 'user'),
            getMessageWithTimestamp(_c, 'assistant')
          ]);
        }  

      }

      return;
    }
    return response;
  } catch (error) {
    throw error;
    console.error("Error sending message to OpenAI: ", error);
  }finally{

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
    case 'warning':
      roleEmoji = '🍄';
      break;
    default:
      roleEmoji = '👾';
  }
  return `${shortTimeString}${roleEmoji}: ${command}`;
}

function Console() {
  const [completionType, setCompletionType] = useState('stream');
  const [maxChars, setMaxChars] = useState(9000);
  const [totalChars, setTotalChars] = useState(0);
  const [remainingChars, setRemainingChars] = useState(0);
  const [inputText, setInputText] = useState('');
  const [content, setContent] = useState([]);
  const [context, setContext] = useState('');
  const [knowledge, setKnowledge] = useState(''); // State for knowledge input
  const [isLoading, setIsLoading] = useState(false); // State to track loading status
  const [tokens, setTokens] = useState('0+0=0');
  const [thinking, setThinking] = useState('🦥');
  const [model, setModel] = useState('gpt-3.5-turbo-1106');
  const [tooBig, setTooBig] = useState('🐁');
  const [message, setMessage] = useState('');
  const contentRef = useRef(null);
  const handleInputChange = (event) => {
    const value = event.target.value;
    setInputText(value);
    handleCharsChange(event);
  };
  const scrollToBottom = () => {
    if (contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }
  const handleContextChange = (event) => {
    const value = event.target.value;
    setContext(value);
    handleCharsChange(event);
  };

  const handleKnowledgeChange = (event) => {
    const value = event.target.value;
    setKnowledge(value);
    handleCharsChange(event);
  };

  const handleCharsChange = (event) => {
    var _remainingChars = 0;
    try {
      var _totalChars = context.length + inputText.length + knowledge.length;
      setTotalChars(_totalChars);
      _remainingChars = maxChars - totalChars;
      setRemainingChars(_remainingChars);
  
      if (_totalChars >= maxChars) {
        setTooBig('🐋'); // Dinosaur emoji for the biggest level
      } else if (_totalChars >= (maxChars * 0.75)) {
        setTooBig('🦕'); // Bear emoji for the third level
      } else if (_totalChars >= (maxChars * 0.5)) {
        setTooBig('🐘'); // Lion emoji for the second level
      } else if (_totalChars >= (maxChars * 0.25)) {
        setTooBig('🐁'); // Mouse emoji for the first level
      }
    } catch (ex) {
      console.warn(ex);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    var command = inputText.trim();
    var message = '';
    console.log('submit:', command);
    setIsLoading(true); // Set loading status to true
    setThinking('🦧');
    try {
      if (command.startsWith('/')) {
        const commandParts = command.split(' ');
        const cmd = commandParts[0];

        switch (cmd) {
          case '/rest':
            setCompletionType('rest');
            message = `Switching to rest completions`;
            break;
          case '/stream':
            setCompletionType('stream');
            message = `Switching to stream completions`;
            break;
          case '/clear':
            setContext('');
            setKnowledge('');
            setContent(['']);
            setInputText('');
            break;
          case '/gpt-3.5-turbo-16k':
            model = 'gpt-3.5-turbo-16k';
            setMaxChars(20000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo-16k`;
            break;
          case '/gpt-3.5-turbo-1106':
            setModel('gpt-3.5-turbo-1106');
            setMaxChars(10000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo-1106`;
            break;
          case '/gpt-3.5-turbo':
            setModel('gpt-3.5-turbo')
            setMaxChars(10000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo`;
            break;
          case '/gpt-4':
            setModel('gpt-4');
            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4`;
            break;
          case '/gpt-4-1106-preview':
            setModel('/gpt-4-1106-preview');
            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4-1106-preview`;
            break;
          case '/help':
            message = 'Commands: ' +
              ' /gpt-3.5-turbo - switch to gpt-3.5-turbo-1106 model (4,096 tokens).' +
              ' /gpt-3.5-turbo-16k - switch to gpt-3.5-turbo-16k model (16,385 tokens).' +
              ' /gpt-3.5-turbo-1106 - switch to gpt-3.5-turbo-1106 model (16,385 tokens).' +
              ' /gpt-4 - switch to gpt-4 model (8,192 tokens).' +
              ' /gpt-4-1106-preview - switch to gpt-4-1106-preview model (128,000 tokens).' +
              ' /help - get help.' +
              ' /clear - clear text boxes.' +
              ' /rest - switch to rest completions.' +
              ' /stream - BROKEN switch to stream completions.' +
              ' /reset - Reset your API key.' +
              ' Indicators: ' +
              ' [3432/9000] - estimated remaining context' +
              ' [rest] - rest completion mode' +
              ' [stream] - stream completion mode.' +
              ' [486+929=1415] - token usage.' +
              ' [🦥] - ready.' +
              ' [🦧] - thinking.' +
              ' [🐋] - context + knowledge + chat is dangerously large.' +
              ' [🦕] - context + knowledge + chat is very large.' +
              ' [🐘] - context + knowledge + chat is large.' +
              ' [🐁] - context + knowledge + chat is acceptable.' +
              ' [gpt-3.5-turbo-1106] - GPT model.';
            break;
          case '/reset':
            localStorage.removeItem('openaiAPIKey');
            window.location.reload();
            break;
          default:
            message = '🍄';
            setMessage('no verbs');
            console.log('No verbs.');

        }
        setContent([
          ...content,
          getMessageWithTimestamp(message, 'system')
        ]);
      } else {
        console.log('content:', command);
        const updatedContext = context ? `${context}\n${command}` : command;
        setContext(updatedContext);
        const response = await sendMessageToOpenAI(command, model, context, knowledge, completionType, setContent, setContext, content, setTokens);
      }
    } catch (ex) {
      console.error('handleSubmit', ex);
      setMessage('error');
      setContent([
        ...content,
        getMessageWithTimestamp(ex, 'error')
      ]);
    } finally {
      setIsLoading(false); // Set loading status to false
      setThinking('🦥');
      setInputText('');
      scrollToBottom();
    }
  };

  return (
    <div className="console">
      <div ref={contentRef} className="console-content">
        {content.map((text, index) => (
          <pre key={index}>{text}</pre>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="input-form">
        <div className="flex-spacer" />
        <div className="char-count">     
          [{totalChars}/{maxChars}][{completionType}][{thinking}][{tooBig}][{message}]
        </div>
        <textarea
          value={context}
          onChange={handleContextChange}
          placeholder="💭"
          className="input-textarea context-textarea"
          aria-label="chat history"
        ></textarea>
        <textarea
          value={knowledge}
          onChange={handleKnowledgeChange}
          placeholder="📝"
          className="input-textarea knowledge-textarea"
          aria-label="knowledge content"
        ></textarea>
        <div className="input-area">
          <textarea
            value={inputText}
            onChange={handleInputChange}
            placeholder="💬"
            className="input-textarea question-textarea"
            aria-label="chat text"
          ></textarea>
          <button type="submit" aria-label="chat submit" className="submit-button">🤖</button>
        </div>
      </form>
    </div>
  );
}

export default Console;
