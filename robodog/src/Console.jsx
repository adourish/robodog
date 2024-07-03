import './Console.css';

import React, { useRef, useEffect, useState } from 'react';
import RobodogLib from '../../robodoglib/dist/robodoglib.bundle.js';
console.log(RobodogLib)
const consoleService = new RobodogLib.ConsoleService()
if(consoleService){
  console.log('index bundle', consoleService)
}
var build = '';
if (window) {
  const version = window.version;
  const buildNumber = window.buildNumber;
  const buildInfo = window.buildInfo;
  build = version + " - " + buildNumber + " - " + buildInfo;
}
console.log(build, consoleService);

function Console() {

  const [completionType, setCompletionType] = useState('stream');
  const [maxChars, setMaxChars] = useState(4096);
  const [totalChars, setTotalChars] = useState(0);
  const [question, setQuestion] = useState('');
  const [content, setContent] = useState([]);
  const [context, setContext] = useState('');
  const [contextButton, setcontextButton] = useState('⬜');
  const [knowledgeTextarea, setknowledgeTextarea] = useState('knowledge-small-textarea');
  const [contextTextarea, setcontextTextarea] = useState('context-small-textarea');
  const [knowledge, setKnowledge] = useState('');
  const [knowledgeButton, setknowledgeButton] = useState('⬜');
  const [thinking, setThinking] = useState('🦥');
  const [model, setModel] = useState('gpt-3.5-turbo');
  const [tooBig, setTooBig] = useState('🐁');
  const [showSettings, setShowSettings] = useState(false);
  const [openAIKey, setOpenAIKey] = useState('')
  const [message, setMessage] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [filter, setFilter] = useState(false);
  const [max_tokens, setMax_tokens] = useState(0);
  const [top_p, setTop_p] = useState(1);
  const [copySuccess, setCopySuccess] = useState('');
  const [frequency_penalty, setFrequency_penalty] = useState(0.0);
  const [presence_penalty, setPresence_penalty] = useState(0.0);
  const [performance, setPerformance] = useState("");
  const [showTextarea, setShowTextarea] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [currentKey, setCurrentKey] = useState('autosave');
  const [size, setSize] = useState('1792x1024');
  const [selectedCommand, setSelectedCommand] = useState('');
  const [commands, setCommands] = useState([]);
  const [options, setOptions] = useState([]);
  const [stashList, setStashList] = useState([]);
  const [formattedCommands, setFormattedCommands] = useState([]);
  const contentRef = useRef(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [selectedOption, setSelectedOption] = useState("");

  useEffect(() => {
    console.log('Component has mounted!');
    if (!isLoaded) {
      var ufo = consoleService.getUFO();
      var _commands = consoleService.getCommands();
      var _options = consoleService.getOptions();
      var _fc = consoleService.getFormattedCommands();
      var _key = consoleService.getAPIKey();
      var list2 = [];
      if (_key && _key != null) {
        console.debug(_key);
        setOpenAIKey(_key);
        const stars = _key.split("").map(char => "*").join("");
        list2 = [consoleService.getMessageWithTimestamp('Your API key is "' + stars + '". To set or update your API key. Please use the command set key command "/key <key>" or reset command "/reset" to remove your key. Or just click ⚙️', 'key')];
      } else {
        list2.push(consoleService.getMessageWithTimestamp('You have not set your API key. Please use the command set key command "/key <key>" or reset command "/reset" to remove your key. Or just click ⚙️', 'key'));
      }
      var list = [consoleService.getMessageWithTimestamp('I want to believe.', 'title')];
      var _l = consoleService.getSettings(build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty);
      var _stashList = consoleService.getStashList();

      if (_stashList) {
        var stashList = _stashList.split(',');
        setStashList(stashList);
      }
      list = list.concat(_l, ufo, list2);

      setCommands(_commands);
      setOptions(_options);
      setIsLoaded(true);
      setContent(list);
      setCurrentKey('autosave');
      setCommands(_commands);
      setFormattedCommands(_fc);
    }
    return () => {
      console.log('Cleaning up...');
    };
  }, [isLoaded, setIsLoaded, size, commands, selectedCommand, setSelectedCommand, setContext, setKnowledge, setQuestion, setContent, setCurrentIndex, setTemperature, setShowTextarea, build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, setCurrentKey, setStashList, setSize, knowledgeTextarea, setknowledgeTextarea, contextTextarea, setcontextTextarea]);

  const setFocusOnLastItem = () => {
    setContent(prevContent => {
      return prevContent.map((item, index) => {
        if (index === prevContent.length - 1) {
          return { ...item, focus: true };
        }
        return item;
      });
    });
  };

  useEffect(() => {
    // Call the function to set focus on the last item when content changes
    setFocusOnLastItem();
  }, [content]);

  const handleSettingsToggle = () => {
    console.debug('handleSettingsToggle', showSettings)
    setShowSettings(!showSettings);
  };
  const handleOpenAIKeyChange = (key) => {
    console.debug('handleOpenAIKeyChange', key);
    consoleService.setAPIKey(key);
    setOpenAIKey(key);
  };
  const handleModelChange = (model) => {
    console.debug('handleModelChange', model);
    setModel(model)
  };
  const handleKeyDown = (event) => {
    if (event.ctrlKey && event.shiftKey && event.keyCode === 38) {
      console.log(currentIndex);
      var total = consoleService.setStashIndex(currentIndex,
        setContext,
        setKnowledge,
        setQuestion,
        setContent,
        setCurrentIndex,
        setCurrentKey,
        setTemperature,
        setShowTextarea);
      if (currentIndex >= total - 1) {
        setCurrentIndex(0);
      } else {
        var _i = currentIndex + 1;
        console.log(_i);
        setCurrentIndex(_i);
      }
    }
  };

  const handleCtrlS = (event) => {
    if (event.ctrlKey && event.keyCode === 83) {
      // Save logic here
      event.preventDefault();
      var key = consoleService.save(context, knowledge, question, content, temperature, showTextarea);
    }
  };

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keydown', handleCtrlS);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keydown', handleCtrlS);
    };
  }, [currentIndex, setContext, setKnowledge, setQuestion, setContent, setCurrentIndex, setTemperature, setShowTextarea, content, context, knowledge, question]);

  const handleInputChange = (event) => {
    const value = event.target.value;
    setQuestion(value);
    handleCharsChange(event);
  };

  const scrollToBottom = () => {
    if (contentRef && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    } else {
      console.debug('no scroll');
    }
  }

  const handleFileUpload = (event) => {
    event.preventDefault();
    setThinking('🦧');
    consoleService.handleImport(setKnowledge, knowledge, setContent, content);
    setThinking('🦥');
  };


  const handleSaveClick = (event) => {
    event.preventDefault();
    setThinking('🦧');
    consoleService.handleExport("save", context, knowledge, question, content, temperature, showTextarea);
    setThinking('🦥');
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
    try {
      var c = consoleService.calculateTokens(context);
      var i = consoleService.calculateTokens(question);
      var k = consoleService.calculateTokens(knowledge);
      var _totalChars = c + i + k;
      setTotalChars(_totalChars);
      var tooBig = consoleService.getTooBigEmoji(_totalChars, maxChars);
      setTooBig(tooBig);

    } catch (ex) {
      console.warn(ex);
    }
  };

  function executeCommands(_command) {
    var message = '';
    var _key;
    var _t;
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
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/clear':
          message = 'Content cleared.';
          setContext('');
          setKnowledge('');
          setQuestion('');
          setContent([consoleService.getMessageWithTimestamp(message, 'warning')]);
          break;
        case '/rest':
          setCompletionType('rest');
          message = `Switching to rest completions`;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/stream':
          setCompletionType('stream');
          message = `Switching to stream completions`;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/list':
          message = 'Stashed items: ' + consoleService.getStashList();
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'event')]);
          break;
        case '/models':
          var list = [];
          consoleService.getEngines().then(data => {
            const startItem = [...content, consoleService.getMessageWithTimestamp(message, 'event')];
            list.push(startItem);
            for (let i = 0; i < data.data.length; i++) {
              const engine = data.data[i];
              const formattedEngine = engine.id + " - " + engine.owner;
              var item = consoleService.getMessageWithTimestamp(formattedEngine, 'event')
              list.push(item);
            }
            setContent(list);

            console.log(data);
          }).catch(err => {
            console.error(err);
          });

          break;
        case '/model':
          setModel(_command.verb);
          message = 'Model is set to ' + _command.verb;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'experiment')]);
          break;
        case '/temperature':
          if (_command.verb) {
            var _t = Number(_command.verb);
            setTemperature(_t);
            setContent([...content, consoleService.getMessageWithTimestamp("Temperature: " + _command.verb, 'experiment')]);
          }
          break;
        case '/toggle':
          if (showTextarea) {
            setShowTextarea(false);
          } else {
            setShowTextarea(true);
          }
          break;
        case '/import':
          consoleService.handleImport(setKnowledge, knowledge, setContent, content);
          break;
        case '/export':
          if (_command.verb) {
            var key = _command.verb;
            consoleService.handleExport(key, context, knowledge, question, content, temperature, showTextarea);
          } else {
            consoleService.handleExport("", context, knowledge, question, content, temperature, showTextarea);
          }
          break;
        case '/max_tokens':
          if (_command.verb) {
            var _t = Number(_command.verb);
            setMax_tokens(_t);
            setContent([...content, consoleService.getMessageWithTimestamp("Max tokens: " + verb, 'experiment')]);
          }
          break;
        case '/top_p':
          if (_command.verb) {
            var _t = Number(_command.verb);
            setTop_p(_t);
            setContent([...content, consoleService.getMessageWithTimestamp("Top P: " + verb, 'experiment')]);
          }
          break;
        case '/frequency_penalty':
          if (_command.verb) {
             _t = Number(_command.verb);
            setFrequency_penalty(_t);
            setContent([...content, consoleService.getMessageWithTimestamp("Frequency Penalty: " + verb, 'experiment')]);
          }
          break;
        case '/presence_penalty':
          if (_command.verb) {
             _t = Number(_command.verb);
            setPresence_penalty(_t);
            setContent([...content, consoleService.getMessageWithTimestamp("Presence Penalty: " + verb, 'experiment')]);
          }
          break;
        case '/get':
          const updatedContext = context ? `${context}\n${_command.verb}` : "";
          setContext(updatedContext);
          consoleService.getTextContent(_command.verb, model, knowledge, setKnowledge).then((content) => {
            setContent([...content, consoleService.getMessageWithTimestamp("/get " + _command.verb, 'user'), consoleService.getMessageWithTimestamp(content, 'event')]);
          });
          break;
        case '/key':
          consoleService.setAPIKey(_command.verb);

           _key = consoleService.getAPIKey();
          message = 'Set API key ' + _key;
          setContext('');
          setKnowledge('');
          setQuestion('');
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'event')]);
          //window.location.reload();
          break;
        case '/getkey':
           _key = consoleService.getAPIKey();
          message = 'Your API key is ' + _key;
          setContext('');
          setKnowledge('');
          setQuestion('');
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'event')]);

          break;


        case '/stash':
          consoleService.stash(_command.verb, context, knowledge, question, content, temperature, showTextarea);
          setCurrentKey(_command.verb);
          message = 'Stashed 💬📝💭 for ' + _command.verb;
          setContext('');
          setKnowledge('');
          setQuestion('');
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'event')]);
          break;
        case '/pop':
          var _pop = consoleService.pop(_command.verb);
          setCurrentKey(_command.verb);
          if (_pop) {
            if (_pop.context) {
              setContext(_pop.context);
            }
            if (_pop.knowledge) {
              setKnowledge(_pop.knowledge);
            }
            if (_pop.question) {
              setQuestion(_pop.question);
            }
            if (_pop.temperature) {
              setQuestion(_pop.temperature);
            }
            if (_pop.showTextarea) {
              setQuestion(_pop.showTextarea);
            }
            if (_pop.content) {
              var _pc = Array.isArray(_pop.content) ? _pop.content : [_pop.content];
              message = 'Popped 💬📝💭 for ' + _command.verb;
              setContent([..._pc, consoleService.getMessageWithTimestamp(message, 'event')]);
            } else {
              message = 'Popped 💬📝💭 for ' + _command.verb;
              setContent([...content, consoleService.getMessageWithTimestamp(message, 'event')]);
            }
          }
          break;
        case '/files':
          consoleService.getUploadedFiles()
            .then(files => {
              console.log('Uploaded Files:', files);
            })
            .catch(error => {
              console.error('Error:', error);
            });
          break;

        case '/dall-e-3':
          setModel('dall-e-3');
          setMaxChars(16385);
          message = `Switching to dall-e-3: dall-e-3 1024x1024, 1024x1792 or 1792x1024`;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-3.5-turbo-16k':
          setModel('gpt-3.5-turbo-16k');
          setMaxChars(16385);
          message = `Switching to GPT-3.5: gpt-3.5-turbo-16k`;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        //gpt-4o
        case '/gpt-4o':
          setModel('gpt-4o');
          setMaxChars(16385);
          message = `Switching to GPT-4o: gpt-4o`;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-3.5-turbo':
          setModel('gpt-3.5-turbo')
          setMaxChars(4096);
          message = `Switching to GPT-3.5: gpt-3.5-turbo`;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-4':
          setModel('gpt-4');
          setMaxChars(8192);
          message = `Switching to GPT-4: gpt-4`;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-4-1106-preview':
          setModel('/gpt-4-1106-preview');
          setMaxChars(128000);
          message = `Switching to GPT-4: gpt-4-1106-preview`;
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/help':
          var _l = consoleService.getHelp('', build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty);
          setContent(_l);
          break;
        case '/reset':
          localStorage.removeItem('openaiAPIKey');
          //window.location.reload();
          setContent([...content, consoleService.getMessageWithTimestamp('reset', 'system')]);
          break;
        default:
          message = '🍄';
          setContent([...content, consoleService.getMessageWithTimestamp(message, 'system')]);
          setMessage('no verbs');
          console.log('No verbs.');
      }
    }
  }
  function handleDropdownChange(event) {
    const selectedValue = event.target.value;
    const selectedOption = options.find((option) => option.command === selectedValue);
    setSelectedOption(selectedOption);

    if (selectedOption && selectedOption.command) {
      var _c = selectedOption.command;

      if (_c.includes("<name>")) {
        const name = prompt("Please enter a name:" + selectedOption.description);
        _c = _c.replace("<name>", name);
      }

      if (_c.includes("<number>")) {
        const number = prompt("Please enter a number:" + selectedOption.description);
        _c = _c.replace("<number>", number);
      }

      setQuestion(_c);
      console.log(_c);
    }
  }

  function handleStashListChange(event) {
    const key = event?.target?.value;
    if (key) {
      ConsoleService.setStashKey(key,
        currentIndex,
        setContext,
        setKnowledge,
        setQuestion,
        setContent,
        setCurrentIndex,
        setCurrentKey,
        setTemperature,
        setShowTextarea);
      console.log(key);
    }
  }
  function copyToClipboard(text) {
    var first6chars = text.substring(0, 6);
    if (text.length < 6) {
      first6chars = text;
    } else {
      setCopySuccess(first6chars);
    }
  
    navigator.clipboard.writeText(text)
      .then(() => {
        setCopySuccess(first6chars);
      })
      .catch(err => {
        setCopySuccess('Failed to copy text ');
      });
  }


  const handleKnowledgeSizeEvent = async (event) => {
    event.preventDefault();
    console.log('handleKnowledgeEvent', knowledgeTextarea)
    if (knowledgeTextarea === 'knowledge-textarea') {
      setknowledgeTextarea('knowledge-big-textarea');
      setknowledgeButton('🟥');
    } else if (knowledgeTextarea === 'knowledge-big-textarea') {
      setknowledgeTextarea('knowledge-small-textarea');
      setknowledgeButton('⬜');
    } else {
      setknowledgeTextarea('knowledge-textarea');
      setknowledgeButton('🟦');
    }
  };
  const handleHistorySizeEvent = async (event) => {
    event.preventDefault();
    console.log('handleHistoryEvent', contextTextarea)
    if (contextTextarea === 'context-textarea') {
      setcontextTextarea('context-big-textarea');
      setcontextButton('🟥');
    } else if (contextTextarea === 'context-big-textarea') {
      setcontextTextarea('context-small-textarea');
      setcontextButton('⬜');
    } else {
      setcontextTextarea('context-textarea');
      setcontextButton('🟦');
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    var command = question.trim();
    console.log('submit:', command);
    setThinking('🦧');
    setMessage('');
    try {
      var _command = consoleService.getVerb(command);
      if (_command.isCommand) {
        executeCommands(_command);
      } else {
        console.log('content:', command);
        const updatedContext = context ? `${context}\n${command}` : command;
        setContext(updatedContext);
        var response = await consoleService.askQuestion(command,
          model,
          context,
          knowledge,
          completionType,
          setContent,
          setContext,
          setMessage,
          content,
          temperature,
          filter,
          max_tokens,
          top_p,
          frequency_penalty,
          presence_penalty,
          scrollToBottom,
          performance,
          setPerformance,
          setThinking,
          currentKey,
          setSize,
          size);
      }
    } catch (ex) {
      console.error('handleSubmit', ex);
      setMessage('error');
      setContent([
        ...content,
        consoleService.getMessageWithTimestamp(ex, 'error')
      ]);
    } finally {
      setThinking('🦥');
      setQuestion('');
      scrollToBottom();
    }
  };

  return (

    <div className="console">
      <div className="top-menu">
        <select onChange={handleDropdownChange}>
          <option disabled selected>
            Select an option
          </option>
          {options.map((option, index) => (
            <option key={index} value={option.command}>
              {option.command} {option.description}
            </option>
          ))}
        </select>
        <select onChange={handleStashListChange}>
          <option disabled selected>
            Select a save point
          </option>
          {stashList.map((item, index) => (
            <option key={index} value={item}>
              {item}
            </option>
          ))}
        </select>
      </div>


      <div className="console-content">
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
          } else if (item.role === 'setting' || item.role === 'help') {
            return (
              <pre class='setting-text' key="{index}" focus="{item.focus}" alt="{item.datetime}{item.roleEmoji}">
                <code>{item.command}</code>
              </pre>
            );
          } else {
            return (
              <pre  class='console-text' key={index} focus={item.focus} onClick={()=>copyToClipboard(item.command)}>
              <code>{`${item.datetime} ${item.roleEmoji}:${item.command}`}</code>
              </pre>
            );
          }
        })}
      </div>
      <form onSubmit={handleSubmit} className="input-form">
        <span className="char-count">
          <label htmlFor="totalChars">[{totalChars}/{maxChars}]</label>
          <label htmlFor="model">[{model}]</label>
          <label htmlFor="temperature" className="status-hidden">[{temperature}]</label>
          <label htmlFor="completionType" className="status-hidden">[{completionType}]</label>
          <label htmlFor="thinking">[{thinking}]</label>
          <label htmlFor="tooBig" className="status-hidden">[{tooBig}]</label>
          <label htmlFor="performance" className="status-hidden">[{performance}]</label>
          <label htmlFor="message">[{message}]</label>
          <label htmlFor="copy">[{copySuccess}]</label>
          <label htmlFor="currentKey" className="status-hidden">[{currentKey}]</label>
          <label htmlFor="size" className="status-hidden">[{size}]</label>
          <button type="button" onClick={handleFileUpload} aria-label="history" className="button-uploader status-hidden" title="Upload File">📤</button>
          <button type="button" onClick={handleSaveClick} aria-label="history" className="button-uploader status-hidden" title="Download">📥</button>
          <button type="button" onClick={handleSettingsToggle} aria-label="settings" className="button-uploader" title="Settings">⚙️</button>
        </span>
        <div className={`settings-content ${showSettings ? 'visible' : 'hidden'}`}>
          <label htmlFor="openAIKey">Open AI key:</label>
          <input
            type="text"
            id="openAIKey"
            className="input-field"
            value={openAIKey}
            onChange={(e) => handleOpenAIKeyChange(e.target.value)}
          />

        </div>
        <div className={`settings-content ${showSettings ? 'visible' : 'hidden'}`}>
          <label htmlFor="model">Model:</label>
          <input
            type="text"
            id="model"
            className="input-field"
            value={model}
            onChange={(e) => handleModelChange(e.target.value)}
          />

        </div>
        <div className="input-area">
          <textarea
            value={context}
            onChange={handleContextChange}
            placeholder="Chat history💭: "
            className={`input-textarea ${contextTextarea}`}
            aria-label="chat history"
          ></textarea>
          <button type="button" onClick={handleHistorySizeEvent} aria-label="history" className="history-button" title="Bigger and Smaller">{contextButton}</button>
        </div>
        <div className="input-area">
          <textarea
            value={knowledge}
            onChange={handleKnowledgeChange}
            placeholder="Knowledge📝: examples, data, code"
            className={`input-textarea ${knowledgeTextarea}`}
            aria-label="knowledge content"
          ></textarea>
          <button type="button" onClick={handleKnowledgeSizeEvent} aria-label="knowledge" className="knowledge-button" title="Bigger and Smaller">{knowledgeButton}</button>
        </div>
        <div className="input-area">
          <textarea
            value={question}
            onChange={handleInputChange}
            placeholder="Chat💬: "
            className="input-textarea question-textarea"
            aria-label="chat text"
          ></textarea>
          <button type="submit" aria-label="chat submit" className="submit-button" title="Ask Question">🤖</button>
        </div>
      </form>
    </div>
  );
}

export default Console;
