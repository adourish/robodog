import './Console.css';
import { v4 as uuidv4 } from 'uuid';

import React, { useRef, useEffect, useState } from 'react';
import RobodogLib from '../../robodoglib/dist/robodoglib.bundle.js';
console.log(RobodogLib)
const consoleService = new RobodogLib.ConsoleService()
const routerService = new RobodogLib.RouterService();
const formatService = new RobodogLib.FormatService();
const providerService = new RobodogLib.ProviderService();
const rtcService = new RobodogLib.RTCService();
const hostService = new RobodogLib.HostService()
const ConsoleContentComponent = RobodogLib.ConsoleContentComponent;
const SettingsComponent = RobodogLib.SettingsComponent;

if (consoleService) {
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
  const [yamlConfig, setYamlConfig] = useState('')
  const [message, setMessage] = useState('');
  const [search, setSearch] = useState('🔎');
  const [temperature, setTemperature] = useState(1);
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
  const [isLoaded, setIsLoaded] = useState(false);
  const [isPWA, setIsPWA] = useState(false);
  const [intervalId, setIntervalId] = useState(0);
  const [watch, setWatch] = useState('');
  const [file, setFile] = useState('');
  const [group, setGroup] = useState('');

  useEffect(() => {
    console.log('Component has mounted!');
    if (!isLoaded) {
      var ufo = consoleService.getUFO();
      var _commands = consoleService.getCommands();
      var _options = consoleService.getOptions();
      var _yamlConfig = providerService.getYaml();
      setYamlConfig(_yamlConfig);
      var _model = providerService.getCurrentModel();
      if (_model && _model !== '') {
        setModel(_model)
      }
      var list = [formatService.getMessageWithTimestamp('I want to believe.', 'title')];
      var _l = consoleService.getSettings(build, _model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty);
      var _stashList = consoleService.getStashList();

      if (_stashList) {
        var stashList = _stashList.split(',');
        setStashList(stashList);
      }
      list = list.concat(_l, ufo);

      setCommands(_commands);
      setOptions(_options);
      setIsLoaded(true);
      setContent(list);
      setCurrentKey('autosave');
      setCommands(_commands);

    }
    return () => {
      clearInterval(intervalId);
      console.log('Cleaning up...');
    };
  }, [intervalId, setIntervalId, isLoaded,
    setIsLoaded,
    size,
    commands,
    selectedCommand,
    setSelectedCommand,
    setContext,
    setKnowledge,
    setQuestion, setContent, setCurrentIndex, setTemperature, setShowTextarea,
    model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty,
    setCurrentKey, setStashList, setSize,
    knowledgeTextarea, setknowledgeTextarea, contextTextarea, setcontextTextarea]);

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

  useEffect(() => {
    try {

      if (window.matchMedia('(display-mode: standalone)').matches) {
        setIsPWA(true);
      } else {
        window.addEventListener('appinstalled', () => {
          setIsPWA(true);
        });
      }
    } catch (error) {
      console.error('Error in detecting PWA', error);
    }
  }, []);

  const handleSettingsToggle = () => {
    console.debug('handleSettingsToggle', showSettings)
    setShowSettings(!showSettings);
  };

  const handleStash = () => {
    try {
      var q = question + ' ' + content
      var verb = q.length < 15 ? q : q.substring(0, 20);
      console.log(verb);
      console.debug('handleStash', "verb")
      consoleService.stash(verb, context, knowledge, question, content, temperature, showTextarea);
      var _stashList = consoleService.getStashList();

      if (_stashList) {
        var stashList = _stashList.split(',');
        setStashList(stashList);
      }
    } catch (ex) {
      console.log("test")
    }
  };


  //handleYamlConfigKeyChange
  const handleYamlConfigKeyChange = (key) => {
    console.debug('handleYamlConfigKeyChange', key);
    providerService.setYaml(key);
    setYamlConfig(key);
  };

  const handleModelChange = (model) => {
    console.debug('handleModelChange', model);
    setModel(model)
  };


  useEffect(() => {
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
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keydown', handleCtrlS);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keydown', handleCtrlS);
    };
  }, [currentIndex, setContext, setKnowledge, setQuestion, showTextarea, temperature, setContent, setCurrentIndex, setTemperature, setShowTextarea, content, context, knowledge, question]);

  const handleInputChange = (event) => {
    const value = event.target.value;
    setQuestion(value);
    handleCharsChange(event);
  };


  const handleFileUpload = (event) => {
    event.preventDefault();
    setThinking('🦧');
    consoleService.handleImport(setKnowledge, knowledge, setContent, content);
    setThinking('🦥');
  };

  const handleSetModel = (event) => {
    var message = 'Model is set to ' + event;
    providerService.setCurrentModel(event)
    setModel(event)
    setContent([...content, formatService.getMessageWithTimestamp(message, 'model')]);
  }


  const handleSetGroup = (event) => {
    var message = 'Group is set to ' + event;
    hostService.setActiveGroup(event)
      .then(() => {
        setGroup(event);
        setContent([...content, formatService.getMessageWithTimestamp(message, 'experiment')]);
      })
      .catch(error => {
        console.error('Error setting active group:', error);
      });
  }

  const handleGetGroups = () => {
    var message = 'Fetching groups';
    hostService.getGroups()
      .then(groups => {
        if (groups && groups.groups && Array.isArray(groups.groups)) {
          const groupNames = groups.map(group => group.name).join(', ');
          setContent([...content, formatService.getMessageWithTimestamp(`Groups: ${groupNames}`, 'experiment')]);
        } else {
          console.error('Error: groups is not an array');
        }
      })
      .catch(error => {
        console.error('Error getting groups:', error);
      });
  }

  const handleSetFile = (event) => {
    var message = 'File is set to ' + event;
    hostService.setActiveFile(event)
      .then(() => {
        setFile(event);
        setContent([...content, formatService.getMessageWithTimestamp(message, 'experiment')]);
      })
      .catch(error => {
        console.error('Error setting active file:', error);
      });
  }

  const handleSetWatch = () => {
    const newWatchState = watch ? '' : '💻';
    hostService.toggleCircuitBreaker(!watch);
    var message = 'Watch is set to ' + newWatchState;

    setWatch(newWatchState);
    setContent([...content, formatService.getMessageWithTimestamp(message, 'experiment')]);
  }
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
    console.debug('handleKnowledgeChange', event)
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
      var tooBig = formatService.getTooBigEmoji(_totalChars, maxChars);
      setTooBig(tooBig);

    } catch (ex) {
      console.warn(ex);
    }
  };

  function executeCommands(_command) {
    var message = '';
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
          setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
          break;
        case '/clear':
          message = 'Content cleared.';
          setContext('');
          setKnowledge('');
          setQuestion('');
          let _m = formatService.getMessageWithTimestamp(message, 'setting');
          console.trace(_m)
          setContent([_m]);
          break;
        case '/rest':
          setCompletionType('rest');
          message = `Switching to rest completions`;
          setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
          break;
        case '/stream':
          setCompletionType('stream');
          message = `Switching to stream completions`;
          setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
          break;
        case '/list':
          message = 'Stashed items: ' + consoleService.getStashList();
          setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
          break;
        case '/models':
          var list = [...content]
          var models = providerService.getModels();
          if (models) {

            for (var i = 0; i < models.length; i++) {
              var engine = models[i];
              const formattedEngine = engine.model;
              var item = formatService.getMessageWithTimestamp(formattedEngine, 'model')
              list.push(item);
            }
          }
          setContent(list);

          console.log(models);

          break;
        case '/model':
          handleSetModel(_command.verb)
          break;
        case '/watch':
          handleSetWatch(_command.verb)
          break;
        case '/file':
          handleSetFile(_command.verb)
          break;
        case '/group':
          handleSetGroup(_command.verb)
          break;
        case '/groups':
          handleGetGroups(_command.verb)
          break;
        case '/search':
          if (search !== '') {
            setSearch('');
          } else {
            setSearch('🔎');
            setModel('search')
          }

          message = 'Search mode active';
          setContent([...content, formatService.getMessageWithTimestamp(message, 'experiment')]);
          break;
        case '/temperature':
          if (_command.verb) {
            var _t = Number(_command.verb);
            setTemperature(_t);
            setContent([...content, formatService.getMessageWithTimestamp("Temperature: " + _command.verb, 'experiment')]);
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
            setContent([...content, formatService.getMessageWithTimestamp("Max tokens: " + _command.verb, 'experiment')]);
          }
          break;
        case '/top_p':
          if (_command.verb) {
            var _t = Number(_command.verb);
            setTop_p(_t);
            setContent([...content, formatService.getMessageWithTimestamp("Top P: " + _command.verb, 'experiment')]);
          }
          break;
        case '/frequency_penalty':
          if (_command.verb) {
            _t = Number(_command.verb);
            setFrequency_penalty(_t);
            setContent([...content, formatService.getMessageWithTimestamp("Frequency Penalty: " + _command.verb, 'experiment')]);
          }
          break;
        case '/presence_penalty':
          if (_command.verb) {
            _t = Number(_command.verb);
            setPresence_penalty(_t);
            setContent([...content, formatService.getMessageWithTimestamp("/get " + _command.verb, 'user'), formatService.getMessageWithTimestamp(content, 'event')]);
            setContent([...content, formatService.getMessageWithTimestamp("Presence Penalty: " + _command.verb, 'experiment')]);
          }
          break;

        case '/stash':
          if (_command.verb === 'clear') {
            consoleService.clearStashList();
            var _stashList = consoleService.getStashList();

            if (_stashList) {
              var stashList = _stashList.split(',');
              setStashList(stashList);
            }
          } else {
            consoleService.stash(_command.verb, context, knowledge, question, content, temperature, showTextarea);
            setCurrentKey(_command.verb);
            message = 'Stashed 💬📝💭 for ' + _command.verb;
            setContext('');
            setKnowledge('');
            setQuestion('');
            setContent([...content, formatService.getMessageWithTimestamp(message, 'event')]);
            var _stashList2 = consoleService.getStashList();

            if (_stashList2) {
              var stashList2 = _stashList2.split(',');
              setStashList(stashList2);
            }
          }
          break;
          case '/replace':
            try {
              // Split the verb into 'from' and 'to' texts
              const args = _command.verb.match(/'([^']+)'/g);
              if (!args || args.length < 2) {
                throw new Error("Invalid syntax. Use /replace 'from text' 'to text'");
              }
              const fromText = args[0].replace(/'/g, '');
              const toText = args[1].replace(/'/g, '');
    
              // Perform the replacement in all content items
              const updatedContent = content.map(item => {
                if (typeof item.text === 'string') {
                  return { ...item, text: item.text.split(fromText).join(toText) };
                }
                return item;
              });
    
              setContent(updatedContent);
              message = `Replaced all instances of '${fromText}' with '${toText}'`;
              setContent([...content, formatService.getMessageWithTimestamp(message, 'setting')]);
            } catch (error) {
              message = error.message;
              setContent([...content, formatService.getMessageWithTimestamp(message, 'error')]);
            }
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
              setContent([..._pc, formatService.getMessageWithTimestamp(message, 'event')]);
            } else {
              message = 'Popped 💬📝💭 for ' + _command.verb;
              setContent([...content, formatService.getMessageWithTimestamp(message, 'event')]);
            }
          }
          break;
        case '/dall-e-3':
          setModel('dall-e-3');
          setMaxChars(16385);
          message = `Switching to dall-e-3: dall-e-3 1024x1024, 1024x1792 or 1792x1024`;
          setContent([...content, formatService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-3.5-turbo-16k':
          handleSetModel('gpt-3.5-turbo-16k')
          setMaxChars(16385);
          message = `Switching to GPT-3.5: gpt-3.5-turbo-16k`;
          setContent([...content, formatService.getMessageWithTimestamp(message, 'system')]);
          break;
        //gpt-4o
        case '/gpt-4o':
          handleSetModel('gpt-4o')
          setMaxChars(16385);
          message = `Switching to GPT-4o: gpt-4o`;
          setContent([...content, formatService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-3.5-turbo':
          handleSetModel('gpt-3.5-turbo')
          setMaxChars(4096);
          message = `Switching to GPT-3.5: gpt-3.5-turbo`;
          setContent([...content, formatService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-4':
          setModel('gpt-4');
          handleSetModel('gpt-4')
          setMaxChars(8192);
          message = `Switching to GPT-4: gpt-4`;
          setContent([...content, formatService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/help':
          var _l = consoleService.getHelp('', build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty);
          setContent(_l);
          break;
        case '/reset':
          providerService.reset();
          console.log('/reset')
          //window.location.reload();
          setContent([...content, formatService.getMessageWithTimestamp('reset', 'system')]);
          break;
        default:
          message = '🍄';
          setContent([...content, formatService.getMessageWithTimestamp(message, 'system')]);
          setMessage('no verbs');
          console.log('No verbs.');
      }

    }
    consoleService.scrollToBottom();
  }
  function handleDropdownChange(event) {
    const selectedValue = event.target.value;
    const selectedOption = options.find((option) => option.command === selectedValue);

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
      consoleService.setStashKey(key,
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

  function handleLaunch(name, url) {
    console.debug('handleLaunch', name, url)

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
  
  // Get the referer URL
  const refererUrl = document.referrer || 'Referer info not available';
  
  try {
    var _command = consoleService.getVerb(command);
    if (_command.isCommand) {
      executeCommands(_command);
      setThinking('🦥');
    } else {
      console.log('content:', command);
      const updatedContext = context ? `${context}\n${command}` : command;
      setContext(updatedContext);
      var routerModel = new RobodogLib.RouterModel(
        question,
        model,
        context,
        knowledge,
        content,
        temperature,
        max_tokens,
        currentKey,
        size,
        setContent,
        setMessage,
        setPerformance,
        setThinking,
        setKnowledge          
      );
      var response = await routerService.routeQuestion(routerModel);
      console.debug(response);
    }
    setThinking('🦥');
  } catch (ex) {
    setThinking('🐛');
    
    // Include referer URL and additional debug information in the error message
    console.error('handleSubmit', ex);
    const errorMessage = `Error occurred: ${ex.message}, Referer URL: ${refererUrl}, Stack: ${ex.stack}`;
    setMessage(errorMessage);
    
    setContent([
      ...content,
      formatService.getMessageWithTimestamp(errorMessage, 'error')
    ]);
  } finally {
    setQuestion('');
    consoleService.scrollToBottom();
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
      <ConsoleContentComponent
        content={content}
        handleCopyToClipboard={copyToClipboard}
        handleSetModel={handleSetModel}
        handleLaunch={handleLaunch}
      />
      <form onSubmit={handleSubmit} className="input-form">
        <span className="char-count">
          <label htmlFor="totalChars">[{totalChars}]</label>
          <label htmlFor="model">[{model}]</label>
          <label htmlFor="temperature" className="status-hidden">[{temperature}]</label>
          <label htmlFor="thinking">[{thinking}]</label>
          <label htmlFor="tooBig" className="status-hidden">[{tooBig}]</label>
          <label htmlFor="performance" className="status-hidden">[{performance}]</label>
          <label htmlFor="message" className="">[{message}]</label>
          <label htmlFor="copy" className="status-hidden">[{copySuccess}]</label>
          <label htmlFor="currentKey" className="status-hidden">[{currentKey}]</label>
          <label htmlFor="watch" className="">[{watch}]</label>
          <label htmlFor="group" className="">[{group}]</label>
          <label htmlFor="file" className="">[{file}]</label>

          <button type="button" onClick={handleFileUpload} aria-label="history" className="button-uploader" title="Upload File">📤</button>
          <button type="button" onClick={handleSaveClick} aria-label="history" className="button-uploader" title="Download">📥</button>
          <button type="button" onClick={handleSettingsToggle} aria-label="settings" className="button-uploader" title="Settings">⚙️</button>
          <button type="button" onClick={handleStash} aria-label="history" className="button-uploader " title="Stash">📍</button>

        </span>
        <SettingsComponent
          showSettings={showSettings}
          yamlConfig={yamlConfig}
          handleYamlConfigKeyChange={handleYamlConfigKeyChange}
        />
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
