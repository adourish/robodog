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
    { role: "user", content: "knowledge:" + knowledge },
    { role: "user", content: "question:" + text + ". Use the content in knowledge and chat history to answer the question." }
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
  } finally {

  }
}

// Function to save content in local storage
function stash(key, context, knowledge, question) {
  const stashKey = "stash-" + key;
  const content = {
    context: context,
    key: key,
    knowledge: knowledge,
    question: question,
    timestamp: new Date().toISOString()
  };

  localStorage.setItem(stashKey, JSON.stringify(content));
}

// Function to get the content from local storage
function pop(key) {
  const stashKey = "stash-" + key;
  const content = localStorage.getItem(stashKey);

  if (content) {
    return JSON.parse(content);
  } else {
    return null;
  }
}

function stashList() {
  const keys = Object.keys(localStorage).filter(key => key.startsWith("stash-"));
  const list = keys.map(key => {
    const content = localStorage.getItem(key);
    const parsedContent = JSON.parse(content);
    return { key: key, timestamp: parsedContent.timestamp };
  });
  var csvString = '';
  if (list) {
    for (var i = 0; i < list.length; i++) {
      var _key = list[i].key;
      csvString += _key.replace('stash-', '');
      if (i < list.length - 1) {
        csvString += ',';
      }
    }
  }
  return csvString;
}

function getVerb(command) {
  var model = { "cmd": "", "verb": "", isCommand: false };
  const commandParts = command.split(' ');
  const cmd = commandParts[0];
  var verb = '';
  if (commandParts.length > 1) {
    verb = commandParts[1];
  } else {

  }
  if (command.startsWith('/')) {
    model.isCommand = true;
  }
  model.cmd = cmd;
  model.verb = verb;
  return model;
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
    case 'event':
      roleEmoji = '👹';
      break;
    case 'error':
      roleEmoji = '💩';
      break;
    case 'warning':
      roleEmoji = '🍄';
      break;
    case 'info':
      roleEmoji = '😹';
      break;
    //experiment
    case 'experiment':
      roleEmoji = '💣';
      break;
    default:
      roleEmoji = '🙀';
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
      var _command = getVerb(command);
      if (_command.isCommand) {

        switch (_command.cmd) {
          case '/clear':
            setContext('');
            setKnowledge('');
            setInputText('');
            setContent([...content, getMessageWithTimestamp(message, 'warning')]);
            break;
          case '/rest':
            setCompletionType('rest');
            message = `Switching to rest completions`;
            setContent([...content, getMessageWithTimestamp(message, 'system')]);
            break;
          case '/stream':
            setCompletionType('stream');
            message = `Switching to stream completions`;
            setContent([...content, getMessageWithTimestamp(message, 'system')]);
            break;
          case '/list':
            message = 'Stashed items: ' + stashList();
            setContent([...content, getMessageWithTimestamp(message, 'event')]);
            break;
          case '/model':
            setModel(_command.verb);
            message = 'Model is set to ' + _command.verb;
            setContent([...content, getMessageWithTimestamp(message, 'experiment')]);
            break;
          case '/stash':
            stash(_command.verb, context, knowledge, inputText);
            message = 'Stashed 💬📝💭 for ' + verb;
            setContext('');
            setKnowledge('');
            setInputText('');
            setContent([...content, getMessageWithTimestamp(message, 'event')]);
            break;
          case '/pop':
            var _pop = pop(verb);
            if (_pop) {
              if (_pop.context) {
                setContext(_pop.context);
              }
              if (_pop.knowledge) {
                setKnowledge(_pop.knowledge);
              }
              if (_pop.question) {
                setInputText(_pop.question);
              }
            }
            message = 'Popped 💬📝💭 for ' + verb;
            setContent([...content, getMessageWithTimestamp(message, 'event')]);
            break;
          case '/gpt-3.5-turbo-16k':
            model = 'gpt-3.5-turbo-16k';
            setMaxChars(20000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo-16k`;
            setContent([...content, getMessageWithTimestamp(message, 'system')]);
            break;
          case '/gpt-4-1106-preview':
            setModel('gpt-3.5-turbo-1106');
            setMaxChars(10000);
            message = `Switching to GPT-4: gpt-4-1106-preview`;
            setContent([...content, getMessageWithTimestamp(message, 'system')]);
            break;
          case '/gpt-3.5-turbo':
            setModel('gpt-3.5-turbo')
            setMaxChars(10000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo`;
            setContent([...content, getMessageWithTimestamp(message, 'system')]);
            break;
          case '/gpt-4':
            setModel('gpt-4');
            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4`;
            setContent([...content, getMessageWithTimestamp(message, 'system')]);
            break;
          case '/gpt-4-1106-preview':
            setModel('/gpt-4-1106-preview');
            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4-1106-preview`;
            setContent([...content, getMessageWithTimestamp(message, 'system')]);
            break;
          case '/help':
            var _l = [...content,
            getMessageWithTimestamp(message, 'info'),
              'Commands: ',
              ' /gpt-3.5-turbo - switch to gpt-3.5-turbo-1106 model (4,096 tokens).',
              ' /gpt-3.5-turbo-16k - switch to gpt-3.5-turbo-16k model (16,385 tokens).',
              ' /gpt-3.5-turbo-1106 - switch to gpt-3.5-turbo-1106 model (16,385 tokens).',
              ' /gpt-4 - switch to gpt-4 model (8,192 tokens).',
              ' /gpt-4-1106-preview - switch to gpt-4-1106-preview model (128,000 tokens).',
              ' [gpt-3.5-turbo-1106] - GPT model.',
              ' /model <name> - set to a specific model.',
              ' /help - get help.',
              ' /clear - clear text boxes.',
              ' /rest - switch to rest completions.',
              ' /stream - BROKEN switch to stream completions.',
              ' /reset - Reset your API key.',
              ' /stash <name> - stash your questions and knowledge.',
              ' /pop <name> - pop your questions and knowledge.',
              ' /list - list of popped your questions and knowledge.',
              ' Indicators: ',
              ' [3432/9000] - estimated remaining context',
              ' [rest] - rest completion mode',
              ' [stream] - stream completion mode.',
              ' [486+929=1415] - token usage.',
              ' [🦥] - ready.',
              ' [🦧] - thinking.',
              ' [🐋] - context + knowledge + chat is dangerously large.',
              ' [🦕] - context + knowledge + chat is very large.',
              ' [🐘] - context + knowledge + chat is large.',
              ' [🐁] - context + knowledge + chat is acceptable.',
              ' [🐘] - context + knowledge + chat is large.',
              ' [🐁] - context + knowledge + chat is acceptable.',
              ' [💭] - Chat History',
              ' [📝] - Knowledge Content',
              ' [💬] - Chat Text',
              ' [👾] - User',
              ' [🤖] - Assistant',
              ' [💾] - System',
              ' [👹] - Event',
              ' [💩] - Error',
              ' [🍄] - Warning',
              ' [😹] - Info',
              ' [💣] - Experiment',
              ' [🙀] - Default',
              ' [🦥] - Ready',
              ' [🦧] - Thinking',
              ' [🐋] - Dangerously large',
              ' [🦕] - Very large'
            ];
            setContent(_l);
            break;
          case '/reset':
            localStorage.removeItem('openaiAPIKey');
            window.location.reload();
            setContent([...content, getMessageWithTimestamp('reset', 'system')]);
            break;
          default:
            message = '🍄';
            setContent([...content, getMessageWithTimestamp(message, 'system')]);
            setMessage('no verbs');
            console.log('No verbs.');

        }

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
