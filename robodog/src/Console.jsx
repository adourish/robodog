import './Console.css';

import React, { useRef, useEffect, useState } from 'react';
import ConsoleService from './ConsoleService';
const version = window.version;
const buildNumber = window.buildNumber;
const build = version + "-" + buildNumber;
console.log(build);


function Console() {


  const [completionType, setCompletionType] = useState('stream');
  const [maxChars, setMaxChars] = useState(9000);
  const [totalChars, setTotalChars] = useState(0);
  const [inputText, setInputText] = useState('');
  const [content, setContent] = useState([]);
  const [context, setContext] = useState('');
  const [knowledge, setKnowledge] = useState('');
  const [tokens, setTokens] = useState('0+0=0');
  const [thinking, setThinking] = useState('🦥');
  const [model, setModel] = useState('gpt-3.5-turbo');
  const [tooBig, setTooBig] = useState('🐁');
  const [message, setMessage] = useState('');
  const contentRef = useRef(null);
  const [temperature, setTemperature] = useState(0.7);
  const [filter, setFilter] = useState(false);
  const [max_tokens, setMax_tokens] = useState(0);
  const [top_p, setTop_p] = useState(1);
  const [frequency_penalty, setFrequency_penalty] = useState(0.0);
  const [presence_penalty, setPresence_penalty] = useState(0.0);
  const [performance, setPerformance] = useState("");
  const [showTextarea, setShowTextarea] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);

  const handleKeyDown = (event) => {
    ConsoleService.setStashIndex(currentIndex, setContext, setKnowledge, setInputText, setContent, setCurrentIndex, event.keyCode);
  }; 
  
  useEffect(() => {   
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

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
  const toggleTextarea = () => {
    setShowTextarea(!showTextarea);
  };
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

      var tooBig = ConsoleService.getTooBigEmoji(_totalChars, maxChars);
      setTooBig(tooBig);

    } catch (ex) {
      console.warn(ex);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    var command = inputText.trim();
    var message = '';
    console.log('submit:', command);
    setThinking('🦧');
    setMessage('');
    try {
      var _command = ConsoleService.getVerb(command);
      if (_command.isCommand) {

        switch (_command.cmd) {
          case '/filter':
            if (filter === true) {
              setFilter(false);
              message = `Set filter true`;
            } else {
              setFilter(true);
              message = `Set filter false`;
            }
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            break;
          case '/clear':
            message = 'Content cleared.';
            setContext('');
            setKnowledge('');
            setInputText('');
            setContent([ConsoleService.getMessageWithTimestamp(message, 'warning')]);
            break;
          case '/rest':
            setCompletionType('rest');
            message = `Switching to rest completions`;
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            break;
          case '/stream':
            setCompletionType('stream');
            message = `Switching to stream completions`;
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            break;
          case '/list':
            message = 'Stashed items: ' + ConsoleService.getStashList();
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'event')]);
            break;
          case '/model':
            setModel(_command.verb);
            message = 'Model is set to ' + _command.verb;
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'experiment')]);
            break;
          case '/temperature':
            if (_command.verb) {
              var _t = Number(_command.verb);
              setTemperature(_t);
              setContent([...content, ConsoleService.getMessageWithTimestamp("Temperature: " + verb, 'experiment')]);
            }
            break;
          case '/toggle':
            if(showTextarea){
              setShowTextarea(false);
            }else{
              setShowTextarea(true);
            }
            break;
          case '/import':
            ConsoleService.handleImport(setKnowledge, knowledge, setContent, content);
            break;
          case '/export':
            if (_command.verb) {
              ConsoleService.handleExport(_command.verb, knowledge, content);
            } else {
              ConsoleService.handleExport("", knowledge, content);
            }
            break;
          case '/max_tokens':
            if (_command.verb) {
              var _t = Number(_command.verb);
              setMax_tokens(_t);
              setContent([...content, ConsoleService.getMessageWithTimestamp("Max tokens: " + verb, 'experiment')]);
            }
            break;
          case '/top_p':
            if (_command.verb) {
              var _t = Number(_command.verb);
              setTop_p(_t);
              setContent([...content, ConsoleService.getMessageWithTimestamp("Top P: " + verb, 'experiment')]);
            }
            break;
          case '/frequency_penalty':
            if (_command.verb) {
              var _t = Number(_command.verb);
              setFrequency_penalty(_t);
              setContent([...content, ConsoleService.getMessageWithTimestamp("Frequency Penalty: " + verb, 'experiment')]);
            }
            break;
          case '/presence_penalty':
            if (_command.verb) {
              var _t = Number(_command.verb);
              setPresence_penalty(_t);
              setContent([...content, ConsoleService.getMessageWithTimestamp("Presence Penalty: " + verb, 'experiment')]);
            }
            break;
          case '/get':
            const updatedContext = context ? `${context}\n${_command.verb}` : "";
            setContext(updatedContext);
            ConsoleService.getTextContent(_command.verb, model, knowledge, setKnowledge).then((content) => {
              setContent([...content, ConsoleService.getMessageWithTimestamp("/get " + _command.verb, 'user'), ConsoleService.getMessageWithTimestamp(content, 'event')]);
            });

            break;
          case '/stash':
            ConsoleService.stash(_command.verb, context, knowledge, inputText, content);
            message = 'Stashed 💬📝💭 for ' + _command.verb;
            setContext('');
            setKnowledge('');
            setInputText('');
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'event')]);
            break;
          case '/pop':
            var _pop = ConsoleService.pop(_command.verb);
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
              if (_pop.content) {
                var _pc = Array.isArray(_pop.content) ? _pop.content : [_pop.content];
                message = 'Popped 💬📝💭 for ' + _command.verb;
                setContent([..._pc, ConsoleService.getMessageWithTimestamp(message, 'event')]);
              } else {
                message = 'Popped 💬📝💭 for ' + _command.verb;
                setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'event')]);
              }
            }
            break;
          case '/gpt-3.5-turbo-16k':
            model = 'gpt-3.5-turbo-16k';

            setMaxChars(20000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo-16k`;
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            break;
          case '/gpt-4-1106-preview':
            setModel('gpt-3.5-turbo-1106');
            setMaxChars(10000);
            message = `Switching to GPT-4: gpt-4-1106-preview`;
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            break;
          case '/gpt-3.5-turbo':
            setModel('gpt-3.5-turbo')
            setMaxChars(10000);
            message = `Switching to GPT-3.5: gpt-3.5-turbo`;
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            break;
          case '/gpt-4':
            setModel('gpt-4');

            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4`;
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            break;
          case '/gpt-4-1106-preview':
            setModel('/gpt-4-1106-preview');
            setMaxChars(20000);
            message = `Switching to GPT-4: gpt-4-1106-preview`;
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            break;
          case '/help':
            var _l = [...content,
            ConsoleService.getMessageWithTimestamp(message, 'info'),
              'settings: ',
            "build: " + build,
            "model: " + model,
            "temperature: " + temperature,
            "max_tokens:" + max_tokens,
            "top_p: " + top_p,
            "frequency_penalty: " + frequency_penalty,
            "presence_penalty: " + presence_penalty,
              ' ',
              'commands: ',
              ' /gpt-3.5-turbo - switch to gpt-3.5-turbo-1106 model (4,096 tokens).',
              ' /gpt-3.5-turbo-16k - switch to gpt-3.5-turbo-16k model (16,385 tokens).',
              ' /gpt-3.5-turbo-1106 - switch to gpt-3.5-turbo-1106 model (16,385 tokens).',
              ' /gpt-4 - switch to gpt-4 model (8,192 tokens).',
              ' /gpt-4-1106-preview - switch to gpt-4-1106-preview model (128,000 tokens).',
              ' [gpt-3.5-turbo-1106] - GPT model.',
              ' /model <name> - set to a specific model.',
              ' ',
              ' /help - get help.',
              ' /import - import files into knowledge .md, .txt, .pdf, .js, .cs, .java, .py, json, .yaml, .php.',
              ' /export <filename> - export knowledge to a file.',
              ' /clear - clear text boxes.',
              ' /rest - switch to rest completions.',
              ' /stream - switch to stream completions.',
              ' /reset - Reset your API key.',
              ' /stash <name> - stash your questions and knowledge.',
              ' /pop <name> - pop your questions and knowledge.',
              ' /list - list of popped your questions and knowledge.',
              ' /temperature <double>.',
              ' /max_tokens <number>.',
              ' /top_p <number>.',
              ' /frequency_penalty <double>.',
              ' /presence_penalty <double>.',
              ' ',
              ' indicators: ',
              ' [3432/9000] - estimated remaining context',
              ' [rest] - rest completion mode',
              ' [stream] - stream completion mode.',
              ' [486+929=1415] - token usage.',
              ' [🦥] - ready.',
              ' [🦧] - thinking.',
              ' [🐋] - 💬📝💭 is dangerously large.',
              ' [🦕] - 💬📝💭 is very large.',
              ' [🐘] - 💬📝💭 is large.',
              ' [🐁] - 💬📝💭 is acceptable.',
              ' [🐘] - 💬📝💭 is large.',
              ' [🐁] - 💬📝💭 is acceptable.',
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
              ' [🦉] - Thinking',
              ' [🐝] - Thinking',
              ' [🐋] - Dangerously large',
              ' [🦕] - Very large',
              ' [🦘, 🐆 , 🦌, 🐕, 🐅, 🐈, 🐢] - Performance'
            ];
            setContent(_l);
            break;
          case '/reset':
            localStorage.removeItem('openaiAPIKey');
            window.location.reload();
            setContent([...content, ConsoleService.getMessageWithTimestamp('reset', 'system')]);
            break;
          default:
            message = '🍄';
            setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
            setMessage('no verbs');
            console.log('No verbs.');

        }

      } else {
        console.log('content:', command);
        const updatedContext = context ? `${context}\n${command}` : command;
        setContext(updatedContext);
        const response = await ConsoleService.sendMessageToOpenAI(command,
          model,
          context,
          knowledge,
          completionType,
          setContent,
          setContext,
          setMessage,
          content,
          setTokens,
          temperature,
          filter,
          max_tokens,
          top_p,
          frequency_penalty,
          presence_penalty,
          scrollToBottom,
          performance,
          setPerformance,
          setThinking);
      

      
      }
    } catch (ex) {
      console.error('handleSubmit', ex);
      setMessage('error');
      setContent([
        ...content,
        ConsoleService.getMessageWithTimestamp(ex, 'error')
      ]);
    } finally {
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

          [{totalChars}/{maxChars}][{model}][{temperature}][{completionType}][{thinking}][{tooBig}][{performance}][{message}]
        </div>
        {showTextarea && (
          <textarea
            value={context}
            onChange={handleContextChange}
            placeholder="Chat history💭"
            className="input-textarea context-textarea"
            aria-label="chat history"
          ></textarea>
        )}
        {showTextarea && (
          <textarea
            value={knowledge}
            onChange={handleKnowledgeChange}
            placeholder="Knowledge📝"
            className="input-textarea knowledge-textarea"
            aria-label="knowledge content"
          ></textarea>
        )}
        <div className="input-area">
          <textarea
            value={inputText}
            onChange={handleInputChange}
            placeholder="Chat💬"
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
