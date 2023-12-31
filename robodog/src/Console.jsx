import './Console.css';

import React, { useRef, useEffect, useState } from 'react';
import ConsoleService from './ConsoleService';
const version = window.version;
const buildNumber = window.buildNumber;
const buildInfo = window.buildInfo;
const build = version + " - " + buildNumber + " - " + buildInfo;

console.log(build);

function Console() {

  const [completionType, setCompletionType] = useState('stream');
  const [maxChars, setMaxChars] = useState(4096);
  const [totalChars, setTotalChars] = useState(0);
  const [question, setQuestion] = useState('');
  const [content, setContent] = useState([]);
  const [context, setContext] = useState('');
  const [knowledge, setKnowledge] = useState('');
  const [thinking, setThinking] = useState('🦥');
  const [model, setModel] = useState('gpt-3.5-turbo');
  const [tooBig, setTooBig] = useState('🐁');
  const [message, setMessage] = useState('');
  const [temperature, setTemperature] = useState(0.7);
  const [filter, setFilter] = useState(false);
  const [max_tokens, setMax_tokens] = useState(0);
  const [top_p, setTop_p] = useState(1);
  const [frequency_penalty, setFrequency_penalty] = useState(0.0);
  const [presence_penalty, setPresence_penalty] = useState(0.0);
  const [performance, setPerformance] = useState("");
  const [showTextarea, setShowTextarea] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [currentKey, setCurrentKey] = useState('autosave');
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
      var ufo = ConsoleService.getUFO();
      var _commands = ConsoleService.getCommands();
      var _options = ConsoleService.getOptions();
      var _fc = ConsoleService.getFormattedCommands();
      var list = [ConsoleService.getMessageWithTimestamp('I want to believe.', 'ufo')];
      var _l = ConsoleService.getSettings(build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty);
      var _stashList = ConsoleService.getStashList();

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
      setFormattedCommands(_fc);
    }
    return () => {
      console.log('Cleaning up...');
    };
  }, [isLoaded, setIsLoaded, commands, selectedCommand, setSelectedCommand, setContext, setKnowledge, setQuestion, setContent, setCurrentIndex, setTemperature, setShowTextarea, build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, setCurrentKey, setStashList]);

  const handleKeyDown = (event) => {
    if (event.shiftKey && event.keyCode === 38) {
      console.log(currentIndex);
      var total = ConsoleService.setStashIndex(currentIndex,
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
      var key = ConsoleService.save(context, knowledge, question, content, temperature, showTextarea);
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
    try {
      var c = ConsoleService.calculateTokens(context);
      var i = ConsoleService.calculateTokens(question);
      var k = ConsoleService.calculateTokens(knowledge);
      var _totalChars = c + i + k;
      setTotalChars(_totalChars);
      var tooBig = ConsoleService.getTooBigEmoji(_totalChars, maxChars);
      setTooBig(tooBig);

    } catch (ex) {
      console.warn(ex);
    }
  };

  function executeCommands(_command) {
    var message = '';
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
          setQuestion('');
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
        case '/models':
          ConsoleService.getEngines().then(data => {
            const formattedEngines = [...content, ConsoleService.getMessageWithTimestamp(message, 'event')];
            for (let i = 0; i < data.data.length; i++) {
              const engine = data.data[i];
              const formattedEngine = engine.id + " - " + engine.owner;
              formattedEngines.push(formattedEngine);
            }
            setContent(formattedEngines);
            console.log(formattedEngines);
            console.log(data);
          }).catch(err => {
            console.error(err);
          });

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
            setContent([...content, ConsoleService.getMessageWithTimestamp("Temperature: " + _command.verb, 'experiment')]);
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
          ConsoleService.handleImport(setKnowledge, knowledge, setContent, content);
          break;
        case '/export':
          if (_command.verb) {
            var key = _command.verb;
            ConsoleService.handleExport(key, context, knowledge, question, content, temperature, showTextarea);
          } else {
            ConsoleService.handleExport("", context, knowledge, question, content, temperature, showTextarea);
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
          ConsoleService.stash(_command.verb, context, knowledge, question, content, temperature, showTextarea);
          setCurrentKey(_command.verb);
          message = 'Stashed 💬📝💭 for ' + _command.verb;
          setContext('');
          setKnowledge('');
          setQuestion('');
          setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'event')]);
          break;
        case '/pop':
          var _pop = ConsoleService.pop(_command.verb);
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
              setContent([..._pc, ConsoleService.getMessageWithTimestamp(message, 'event')]);
            } else {
              message = 'Popped 💬📝💭 for ' + _command.verb;
              setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'event')]);
            }
          }
          break;
        case '/files':
          ConsoleService.getUploadedFiles()
            .then(files => {
              console.log('Uploaded Files:', files);
            })
            .catch(error => {
              console.error('Error:', error);
            });
          break;
        case '/upload':
          ConsoleService.uploadContentToOpenAI(_command.verb, knowledge)
            .then(fileId => {
              console.log('File ID:', fileId);
            })
            .catch(error => {
              console.error('Error:', error);
            });

          break;
        case '/gpt-3.5-turbo-16k':
          model = 'gpt-3.5-turbo-16k';
          setMaxChars(16385);
          message = `Switching to GPT-3.5: gpt-3.5-turbo-16k`;
          setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-3.5-turbo':
          setModel('gpt-3.5-turbo')
          setMaxChars(4096);
          message = `Switching to GPT-3.5: gpt-3.5-turbo`;
          setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-4':
          setModel('gpt-4');
          setMaxChars(8192);
          message = `Switching to GPT-4: gpt-4`;
          setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/gpt-4-1106-preview':
          setModel('/gpt-4-1106-preview');
          setMaxChars(128000);
          message = `Switching to GPT-4: gpt-4-1106-preview`;
          setContent([...content, ConsoleService.getMessageWithTimestamp(message, 'system')]);
          break;
        case '/help':
          var _l = ConsoleService.getHelp('', build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty);
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

  function handleVerbChange(event) {
    const verb = event.target.value;
    setCommand(verb);
  }

  function onExecuteCommandsClick(event) {
    console.log(event)
  }
  const handleSubmit = async (event) => {
    event.preventDefault();
    var command = question.trim();
    var message = '';
    console.log('submit:', command);
    setThinking('🦧');
    setMessage('');
    try {
      var _command = ConsoleService.getVerb(command);
      if (_command.isCommand) {
        executeCommands(_command);
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
          currentKey);
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
      <div ref={contentRef} className="console-content">
        {content.map((text, index) => (
          <pre key={index}>{text}</pre>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="input-form">
        <div className="char-count">
          [{totalChars}/{maxChars}][{model}][{temperature}][{completionType}][{thinking}][{tooBig}][{performance}][{message}][{currentKey}]
        </div>
        {showTextarea && (
          <textarea
            value={context}
            onChange={handleContextChange}
            placeholder="Chat history💭: "
            className="input-textarea context-textarea"
            aria-label="chat history"
          ></textarea>
        )}
        {showTextarea && (
          <textarea
            value={knowledge}
            onChange={handleKnowledgeChange}
            placeholder="Knowledge📝: examples, data, code"
            className="input-textarea knowledge-textarea"
            aria-label="knowledge content"
          ></textarea>
        )}
        <div className="input-area">
          <textarea
            value={question}
            onChange={handleInputChange}
            placeholder="Chat💬: "
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
