import './Console.css';
import { v4 as uuidv4 } from 'uuid';

import React, { useRef, useEffect, useState } from 'react';
import RobodogLib from '../../robodoglib/dist/robodoglib.bundle.js';
const consoleService = new RobodogLib.ConsoleService()
const routerService = new RobodogLib.RouterService();
const formatService = new RobodogLib.FormatService();
const providerService = new RobodogLib.ProviderService();
const mcpService = new RobodogLib.MCPService();
const ConsoleContentComponent = RobodogLib.ConsoleContentComponent;
const SettingsComponent = RobodogLib.SettingsComponent;

var build = '';
if (window) {
  const version = window.version;
  const buildNumber = window.buildNumber;
  const buildInfo = window.buildInfo;
  build = version + " - " + buildNumber + " - " + buildInfo;
}
console.log(build, consoleService);

// File Tree Node Component
const FileTreeNode = ({ node, onSelect, onExpand, expandedNodes }) => {
  const isExpanded = expandedNodes[node.path];
  const isDir = node.type === 'directory';

  return (
    <div className="file-tree-node">
      <div
        className={`file-tree-item ${node.type}`}
        onClick={() => isDir ? onExpand(node) : onSelect(node)}
      >
        {isDir && (
          <span className="expand-icon">
            {isExpanded ? '📂' : '📁'}
          </span>
        )}
        {!isDir && <span className="file-icon">📄</span>}
        <span className="file-name">{node.name}</span>
      </div>
      {isExpanded && node.children && (
        <div className="file-children">
          {node.children.map(child => (
            <FileTreeNode
              key={child.path}
              node={child}
              onSelect={onSelect}
              onExpand={onExpand}
              expandedNodes={expandedNodes}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// Task Item Component
const TaskItem = ({ task, onRun, runningTaskId }) => {
  const getStatusEmoji = (status) => {
    switch (status) {
      case 'To Do': return '⬜';
      case 'Doing': return '🔄';
      case 'Done': return '✅';
      default: return '⬜';
    }
  };

  const getProgress = (task) => {
    const tokens = task._token_count || 0;
    const maxTokens = 4000; // Adjust based on your model limits
    return Math.min(100, (tokens / maxTokens) * 100);
  };

  return (
    <div className="task-item">
      <div className="task-header">
        <span className="task-status">{getStatusEmoji(task.status)}</span>
        <span className="task-desc">{task.desc}</span>
        {task.status === 'To Do' && (
          <button
            className="run-task-btn"
            onClick={() => onRun(task)}
            disabled={runningTaskId !== null}
          >
            {runningTaskId === task.id ? '⏳' : '▶️'}
          </button>
        )}
      </div>

      {task.status !== 'To Do' && (
        <div className="task-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${getProgress(task)}%` }}
            ></div>
          </div>
          <div className="token-count">
            Tokens: {task._token_count || 0}
          </div>
        </div>
      )}

      {task.out && (
        <div className="task-focus-file">
          Focus: <code>{task.out.pattern}</code>
        </div>
      )}
    </div>
  );
};

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
  const [commands, setCommands] = useState([]);
  const [options, setOptions] = useState([]);
  const [stashList, setStashList] = useState([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isPWA, setIsPWA] = useState(false);
  const [intervalId, setIntervalId] = useState(0);
  const [watch, setWatch] = useState('');
  const [file, setFile] = useState('');
  const [group, setGroup] = useState('');

  // Todo Task Viewer States
  const [tasks, setTasks] = useState([]);
  const [runningTaskId, setRunningTaskId] = useState(null);
  const [todoViewerVisible, setTodoViewerVisible] = useState(false);

  // File Browser States
  const [fileTree, setFileTree] = useState([]);
  const [expandedNodes, setExpandedNodes] = useState({});
  const [fileViewerVisible, setFileViewerVisible] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');

  // Live Log Feed States
  const [logFeedVisible, setLogFeedVisible] = useState(false);
  const [logs, setLogs] = useState([]);

  // RUN THIS ONCE
  useEffect(() => {
    console.log('Component has mounted!');
    // all your setup logic here, was previously guarded by isLoaded
    var _commands = consoleService.getCommands();
    var _options = consoleService.getOptions();
    var _yamlConfig = providerService.getYaml();
    setYamlConfig(_yamlConfig);
    var _model = providerService.getCurrentModel();
    if (_model && _model !== '') {
      setModel(_model)
    }
    setContent([...content,
    formatService.getMessageWithTimestamp(build, 'setting'),
    formatService.getMessageWithTimestamp(_model, 'setting')]);
    var _stashList = consoleService.getStashList();
    if (_stashList) {
      var stashList = _stashList.split(',');
      setStashList(stashList);
    }
    setCommands(_commands);
    setOptions(_options);
    setIsLoaded(true);
    setCurrentKey('autosave');
    // no repeated setCommands

    return () => {
      clearInterval(intervalId);
      console.log('Cleaning up...');
    };
  }, []);

  useEffect(() => {
    consoleService.scrollToBottom();
  }, [content]);

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
        event.preventDefault();
        consoleService.save(context, knowledge, question, content, temperature, showTextarea);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keydown', handleCtrlS);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keydown', handleCtrlS);
    };
  }, [currentIndex, context, knowledge, question, content, showTextarea, temperature]);

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

  const handleYamlConfigKeyChange = (key) => {
    console.debug('handleYamlConfigKeyChange', key);
    providerService.setYaml(key);
    setYamlConfig(key);
  };

  const handleModelChange = (model) => {
    console.debug('handleModelChange', model);
    setModel(model)
  };

  // --- theme toggler ---
  const THEME_KEY = 'robodog:theme';

  function applyDarkMode() {
    document.body.classList.remove('light-mode');
    localStorage.setItem(THEME_KEY, 'dark');
  }

  function applyLightMode() {
    document.body.classList.add('light-mode');
    localStorage.setItem(THEME_KEY, 'light');
  }

  function toggleDarkMode() {
    if (document.body.classList.contains('light-mode')) {
      applyDarkMode();
    } else {
      applyLightMode();
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
          let modelsText = '';
          if (models) {

            for (var i = 0; i < models.length; i++) {
              var engine = models[i];
              modelsText += "\n";
              modelsText += "" + engine.model + ": " + engine.about + "\n";
            }
          }
          var item = formatService.getMessageWithTimestamp(modelsText, 'model')
          list.push(item);
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
        case '/dark':
          toggleDarkMode();
          const now = document.body.classList.contains('light-mode') ? 'light' : 'dark';
          setContent([
            ...content,
            formatService.getMessageWithTimestamp(
              `Switched to ${now} mode`,
              'setting'
            )
          ]);
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
        case '/todo':
          loadTodoTasks();            // Load tasks immediately
          message = 'Todo viewer opened. Run next or select a task.';
          setContent([
            ...content,
            formatService.getMessageWithTimestamp(message, 'event')
          ]);
          break;

        case '/list_todo_tasks':
          loadTodoTasks();  // Reload and log
          if (tasks.length > 0) {
            message = 'Todo tasks: ' + tasks.map(t => `${t.desc} (${t.status})`).join(', ');
          } else {
            message = 'No todo tasks found.';
          }
          setContent([
            ...content,
            formatService.getMessageWithTimestamp(message, 'event')
          ]);
          break;

        
        case '/files':
          setFileViewerVisible(true);
          loadFileTree();
          break;
        case '/logs':
          setLogFeedVisible(true);
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

  const handleInputChange = (event) => {
    const value = event.target.value;
    setQuestion(value);
    handleCharsChange(event);
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
          setKnowledge,
          setTotalChars
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

  const handleMapCommand = async (subcommand, args) => {
    let message = '';
    let list = [...content];
    
    try {
      switch(subcommand) {
        case 'scan':
          message = '🗺️ Scanning codebase...';
          list.push(formatService.getMessageWithTimestamp(message, 'setting'));
          setContent(list);
          
          const scanResult = await providerService.callMCP('MAP_SCAN', {});
          message = `Scanned ${scanResult.file_count} files, ${scanResult.class_count} classes, ${scanResult.function_count} functions`;
          list.push(formatService.getMessageWithTimestamp(message, 'model'));
          setContent(list);
          break;
          
        case 'find':
          if (!args || args.length === 0) {
            message = 'Usage: /map find <name>';
            list.push(formatService.getMessageWithTimestamp(message, 'setting'));
            setContent(list);
            return;
          }
          
          const findResult = await providerService.callMCP('MAP_FIND', { name: args[0] });
          if (findResult.results && findResult.results.length > 0) {
            message = `Found ${findResult.results.length} definition(s):\n`;
            findResult.results.forEach(r => {
              message += `\n${r.type}: ${r.name} at ${r.file}:${r.line_start}`;
              if (r.docstring) message += `\n  ${r.docstring}`;
            });
          } else {
            message = `No definition found for '${args[0]}'`;
          }
          list.push(formatService.getMessageWithTimestamp(message, 'model'));
          setContent(list);
          break;
          
        case 'context':
          if (!args || args.length === 0) {
            message = 'Usage: /map context <task description>';
            list.push(formatService.getMessageWithTimestamp(message, 'setting'));
            setContent(list);
            return;
          }
          
          const taskDesc = args.join(' ');
          const contextResult = await providerService.callMCP('MAP_CONTEXT', { task_description: taskDesc });
          message = `Context for: ${taskDesc}\nKeywords: ${contextResult.context.keywords.join(', ')}\nRelevant files: ${contextResult.context.total_files}\n`;
          
          const topFiles = Object.entries(contextResult.context.relevant_files).slice(0, 5);
          topFiles.forEach(([path, info]) => {
            message += `\n[${info.score}] ${path.split('/').pop()}`;
          });
          
          list.push(formatService.getMessageWithTimestamp(message, 'model'));
          setContent(list);
          break;
          
        case 'save':
          await providerService.callMCP('MAP_SAVE', { output_path: 'codemap.json' });
          message = '💾 Code map saved to codemap.json';
          list.push(formatService.getMessageWithTimestamp(message, 'setting'));
          setContent(list);
          break;
          
        case 'load':
          const loadResult = await providerService.callMCP('MAP_LOAD', { input_path: 'codemap.json' });
          message = `📂 Code map loaded: ${loadResult.file_count} files`;
          list.push(formatService.getMessageWithTimestamp(message, 'setting'));
          setContent(list);
          break;
          
        default:
          message = 'Map commands: scan, find <name>, context <task>, save, load';
          list.push(formatService.getMessageWithTimestamp(message, 'setting'));
          setContent(list);
      }
    } catch (error) {
      message = `Error: ${error.message}`;
      list.push(formatService.getMessageWithTimestamp(message, 'system'));
      setContent(list);
    }
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

  const handleSaveClick = (event) => {
    event.preventDefault();
    setThinking('🦧');
    consoleService.handleExport("save", context, knowledge, question, content, temperature, showTextarea);
    setThinking('🦥');
  };

  const handleContextChange = (event) => {
    setContext(event.target.value);
    handleCharsChange(event);
  };

  function handleLaunch(name, url) {
    console.debug('handleLaunch', name, url)

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

  const handleKnowledgeChange = (event) => {
    setKnowledge(event.target.value);
    handleCharsChange(event);
  };

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

  // on mount, restore last theme:
  useEffect(() => {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === 'light') {
      applyLightMode();
    } else {
      applyDarkMode();
    }
  }, []);

  // Todo Task Viewer Functions
  const loadTodoTasks = async () => {
    try {
      const response = await mcpService.callMCP("LIST_TODO_TASKS", {});
      setTasks(response.tasks || []);  // Assumes response.tasks is an array of { id, desc, status, ... }
    } catch (error) {
      console.error("Failed to load todo tasks:", error);
      setTasks([]);  // Clear on error
    }
  };

  const runNextTask = async () => {
    try {
      setRunningTaskId(-1);  // Indicate "running next"
      await mcpService.callMCP("TODO", {});  // Runs the next To Do task via TodoService.run_next_task
      await loadTodoTasks();  // Reload after running
    } catch (error) {
      console.error("Failed to run next task:", error);
      setMessage("Error running next task: " + error.message);
    } finally {
      setRunningTaskId(null);
    }
  };

  const runSpecificTask = async (task) => {
    try {
      setRunningTaskId(task.id);
      // Optionally pass task details if your MCP server supports it (e.g., add to payload)
      await mcpService.callMCP("TODO", { taskId: task.id });  // Extend server-side to handle specific IDs if needed
      await loadTodoTasks();  // Reload after running
    } catch (error) {
      console.error("Failed to run task:", error.message);
      setMessage("Error running task: " + error.message);
    } finally {
      setRunningTaskId(null);
    }
  };


  // File Browser Functions
  const loadFileTree = async () => {
    try {
      const response = await mcpService.callMCP("LIST_FILES", {});
      setFileTree(response.files || []);
    } catch (error) {
      console.error("Failed to load file tree:", error);
      setFileTree([]); // Set empty array on error
    }
  };

  const handleFileSelect = async (node) => {
    try {
      setSelectedFile(node);
      const response = await mcpService.callMCP("READ_FILE", { path: node.path });
      setFileContent(response.content);
    } catch (error) {
      console.error("Failed to read file:", error);
      setFileContent("Error reading file");
    }
  };

  const handleNodeExpand = async (node) => {
    if (node.type !== 'directory') return;

    try {
      // Toggle expanded state
      setExpandedNodes(prev => ({
        ...prev,
        [node.path]: !prev[node.path]
      }));

      // If expanding and no children, load them
      if (!prev[node.path] && !node.children) {
        const response = await mcpService.callMCP("LIST_FILES", { path: node.path });
        // Update the tree with children - this would need more complex state management
        // For simplicity, we'll skip this in the mock
      }
    } catch (error) {
      console.error("Failed to expand node:", error);
    }
  };

  // Live Log Feed Functions
  // In a real implementation, you would connect to a WebSocket or use long-polling
  // For demonstration, we'll simulate log entries
  useEffect(() => {
    if (logFeedVisible) {
      const interval = setInterval(() => {
        // Simulate receiving log entries
        const logEntry = {
          timestamp: new Date().toISOString(),
          level: ['info', 'warning', 'error'][Math.floor(Math.random() * 3)],
          message: `Log entry ${logs.length + 1}`
        };
        setLogs(prev => [...prev, logEntry]);
      }, 3000);

      return () => clearInterval(interval);
    }
  }, [logFeedVisible, logs.length]);

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

      {/* Todo Task Viewer */}
      {todoViewerVisible && (
        <div className="todo-viewer">
          <div className="todo-header">
            <h3>Todo Tasks</h3>
            <button onClick={runNextTask} disabled={runningTaskId !== null}>
              {runningTaskId === -1 ? '⏳ Running...' : '▶️ Run Next Task'}
            </button>
            <button onClick={() => setTodoViewerVisible(false)}>×</button>
          </div>
          <div className="task-list">
            {tasks.map(task => (
              <TaskItem
                key={task.id}
                task={task}
                onRun={runSpecificTask}
                runningTaskId={runningTaskId}
              />
            ))}
          </div>
        </div>
      )}

      {/* File Browser */}
      {fileViewerVisible && (
        <div className="file-browser">
          <div className="file-tree-panel">
            <h3>File Explorer</h3>
            <button onClick={() => setFileViewerVisible(false)} className="close-button">×</button>
            {fileTree.map(node => (
              <FileTreeNode
                key={node.path}
                node={node}
                onSelect={handleFileSelect}
                onExpand={handleNodeExpand}
                expandedNodes={expandedNodes}
              />
            ))}
          </div>
          {selectedFile && (
            <div className="file-content-panel">
              <h3>{selectedFile.name}</h3>
              <button onClick={() => setSelectedFile(null)} className="close-button">×</button>
              <pre className="file-content">{fileContent}</pre>
            </div>
          )}
        </div>
      )}

      {/* Live Log Feed */}
      {logFeedVisible && (
        <div className="log-feed">
          <h3>Live Logs</h3>
          <button onClick={() => setLogFeedVisible(false)} className="close-button">×</button>
          <div className="log-messages">
            {logs.map((log, index) => (
              <div key={index} className={`log-entry ${log.level}`}>
                <span className="log-timestamp">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                <span className="log-level">[{log.level.toUpperCase()}]</span>
                <span className="log-message">{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

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
            placeholder="Context History: "
            className={`input-textarea ${contextTextarea}`}
            aria-label="chat history"
          ></textarea>
          <button type="button" onClick={handleHistorySizeEvent} aria-label="history" className="history-button" title="Bigger and Smaller">{contextButton}</button>
        </div>
        <div className="input-area">
          <textarea
            value={knowledge}
            onChange={handleKnowledgeChange}
            placeholder="Knowledge:"
            className={`input-textarea ${knowledgeTextarea}`}
            aria-label="knowledge content"
          ></textarea>
          <button type="button" onClick={handleKnowledgeSizeEvent} aria-label="knowledge" className="knowledge-button" title="Bigger and Smaller">{knowledgeButton}</button>
        </div>
        <div className="input-area">
          <textarea
            value={question}
            onChange={handleInputChange}
            placeholder="Ask: "
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