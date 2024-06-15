import OpenAI from 'openai';
import axios from 'axios';
import { PerformanceCalculator } from './PerformanceCalculator';
import FormatService from './FormatService';
import FileService from './FileService';

const openai = new OpenAI({
  apiKey: getAPIKey(),
  dangerouslyAllowBrowser: true,
});

function calculateTokens(text) {
  text = text.trim();
  var tokens = text.match(/\S+/g) || [];
  return tokens.length;
}

function getMessageWithTimestamp(command, role) {
  var s = FormatService.getMessageWithTimestamp(command, role);
  return s;
}
function save(context, knowledge, question, content, temperature, showTextarea) {
  const currentDate = new Date();
  const formattedDate = currentDate.toISOString().slice(0, 19).replace(/[-T:]/g, '');
  var key = "snapshot" + "-" + formattedDate;
  stash(key, context, knowledge, question, content, temperature,)
  handleExport(key, context, knowledge, question, content, temperature, showTextarea);
  return key;
}

function handleExport(fileName, context, knowledge, question, content, temperature, showTextarea) {
  const currentDate = new Date();
  const formattedDate = currentDate.toISOString().slice(0, 19).replace(/[-T:]/g, '');
  if (!fileName) {
    fileName = `${formattedDate}.txt`;
  }

  let concatenatedString = '';


  if (Array.isArray(content)) {
    for (let i = 0; i < content.length; i++) {
      concatenatedString += content[i] + "\n";
    }
  }
  var fileContent = "Temperature:" + temperature + "\n\n Question:\n\n" + question + "\n\nChat history:\n\n" + context + "\n\nKnowledge:\n\n" + knowledge + '\n\nContent:\n\n' + concatenatedString + '\n\n';

  const element = document.createElement('a');
  element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(fileContent));
  element.setAttribute('download', fileName);
  element.style.display = 'none';
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
}


function handleImport(setKnowledge, knowledge, setContent, content) {
  console.debug("handleUpload")
  FileService.extractFileContent(setContent, content)
    .then((text) => {
      console.log(text);
      var _k = knowledge + "\n" + text;
      setKnowledge(_k);
      setContent([
        ...content,
        FormatService.getMessageWithTimestamp(text, 'assistant')
      ]);
    })
    .catch((error) => {
      setContent([
        ...content,
        FormatService.getMessageWithTimestamp(error, 'assistant')
      ]);
      console.error(error);
    });
}
function getSettings(build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty) {
  var settings = ['settings: ',
    "build: " + build,
    "model: " + model,
    "temperature: " + temperature,
    "max_tokens:" + max_tokens,
    "top_p: " + top_p,
    "frequency_penalty: " + frequency_penalty,
    "presence_penalty: " + presence_penalty];
  var commands = settings.map((line, index) => {
    return {
      "datetime": "",
      "role": "setting",
      "roleEmoji": "",
      "command": line,
      "url": ""
    };
  });
  return commands;
}
const _options = [
  {
    "command": "/gpt-3.5-turbo",
    "description": "Use gpt-3.5-turbo-1106 model (4,096 tokens)"
  },
  {
    "command": "/gpt-3.5-turbo-16k",
    "description": "Use gpt-3.5-turbo-16k model (16,385 tokens)"
  },
  {
    "command": "/gpt-3.5-turbo-1106",
    "description": "Use gpt-3.5-turbo-1106 model (16,385 tokens)"
  },
  {
    "command": "/gpt-4",
    "description": "Use gpt-4 model (8,192 tokens)"
  },
  {
    "command": "/gpt-4-1106-preview",
    "description": "Use gpt-4-1106-preview model (128,000 tokens)"
  },
  {
    "command": "/model <name>",
    "description": "Use model <name>"
  },
  {
    "command": "/help",
    "description": "Get help."
  },
  {
    "command": "/import",
    "description": "Import files into knowledge (.md, .txt, .pdf, .js, .cs, .java, .py, json, .yaml, .php, .csv, .json)"
  },
  {
    "command": "/export <name>",
    "description": "Export knowledge to a file."
  },
  {
    "command": "/clear",
    "description": "Clear screen."
  },
  {
    "command": "/rest",
    "description": "Use rest completions"
  },
  {
    "command": "/stream",
    "description": "Use stream completions"
  },
  {
    "command": "/reset",
    "description": "Reset API key"
  },
  {
    "command": "/stash <name>",
    "description": "Stash questions and knowledge"
  },
  {
    "command": "/pop <name>",
    "description": "Pop questions and knowledge"
  },
  {
    "command": "/list",
    "description": "list stashed questions and knowledge"
  },
  {
    "command": "/temperature <number>",
    "description": "Temperature is a number between 0 and 2, Default value of 1 or 0.7 depending on the model."
  },
  {
    "command": "/max_tokens <number>",
    "description": "Set max tokens."
  },
  {
    "command": "/top_p <number>",
    "description": "Set top p."
  },
  {
    "command": "/frequency_penalty <number>",
    "description": "Set frequency penalty."
  },
  {
    "command": "/presence_penalty <number>",
    "description": "Set presence penalty."
  },
  {
    "command": "CTRL+SHIFT+UP",
    "description": "Cycle through stash list."
  },
  {
    "command": "CTRL+S",
    "description": "Save a snapshot to storage."
  }
];
function getCommands() {
  var commands = [];
  for (var i = 0; i < _options.length; i++) {
    var command = _options[i].command;
    var description = _options[i].description;

    var item = {
      "datetime": "",
      "role": "setting",
      "roleEmoji": "",
      "command": ' ' + command + ' - ' + description,
      "url": ""
    };

    commands.push(item);
  }

  return commands;
}
function getOptions() {
  return _options;
}
function getFormattedCommands() {
  var options = getOptions();
  var commands = ['commands:'];

  for (var i = 0; i < options.length; i++) {
    var option = options[i];
    var command = option.command;
    var description = option.description;
    commands.push(` ${command} - ${description}`);
  }

  return commands;
}
function getIndicators() {
  var indicators = [' indicators: ',
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
    ' [🦘, 🐆 , 🦌, 🐕, 🐅, 🐈, 🐢] - Performance'];

  var commands = indicators.map((line, index) => {
    return {
      "datetime": "",
      "role": "setting",
      "roleEmoji": "",
      "command": line,
      "url": ""
    };
  });
  return commands;

}
function getHelp(message, build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty) {
  var list = [getMessageWithTimestamp(message, 'info')];
  var settings = getSettings(build, model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty);
  var commands = getCommands();
  var indicators = getIndicators();
  getMessageWithTimestamp(message, 'info');
  var list = list.concat(settings, commands, indicators);
  return list;
}

function getUFO() {
  var ufo = [
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⠤⠶⣷⠲⠤⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣤⠞⢉⠀⠀⠀⠿⠦⠤⢦⣍⠲⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⡤⣤⡞⢡⡶⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⢀⣤⠴⠒⣾⠿⢟⠛⠻⣿⡿⣭⠿⠁⢰⠰⠀⠀⠀⠄⣄⣀⡀⠀⠀⠘⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⢰⣿⣿⣦⡀⠙⠛⠋⠀⠀⠉⠻⠿⢷⣦⣿⣤⣤⣤⣤⣀⣈⠉⠛⠽⣆⡒⣿⣯⣷⣄⠀⠀⠀⠀⠀⠀',
    '⠀⠻⣍⠻⠿⣿⣦⣄⡀⢠⣾⠑⡆⠀⠈⠉⠛⠛⢿⡿⠿⠿⢿⣿⣿⣿⣿⠟⠉⠉⢿⣟⢲⢦⣀⠀⠀',
    '⠀⠀⠈⠙⠲⢤⣈⠉⠛⠷⢿⣏⣀⡀⠀⠀⠀⢰⣏⣳⠀⠀⠀⠀⠀⣸⣓⣦⠀⠀⠈⠛⠟⠃⣈⣷⡀',
    '⠀⠀⠀⠀⠀⠈⢿⣙⡓⣶⣤⣤⣀⡀⠀⠀⠀⠈⠛⠁⠀⠀⠀⠀⠀⠹⣿⣯⣤⣶⣶⣶⣿⠘⡿⢸⡿',
    '⠀⠀⠀⠀⠀⠀⠀⠙⠻⣿⡛⠻⢿⣯⣽⣷⣶⣶⣤⣤⣤⣤⣄⣀⣀⢀⣀⢀⣀⣈⣥⡤⠶⠗⠛⠋⠀',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠓⠲⣬⣍⣉⡉⠙⠛⠛⠛⠉⠙⠉⠙⠉⣹⣿⠿⠛⠁⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡼⠃⠀⠀⠉⠉⠉⠻⡗⠒⠒⠚⠋⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡴⠋⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⠀⠀⠀⠀⡴⠋⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⠀⠀⣠⠞⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⣠⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠐⠀⠀⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⢀⠔⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠔⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠐⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀',
    '⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠃⠀⠀⠀'
  ];
  var commands = ufo.map((line, index) => {
    return {
      "datetime": "",
      "role": "ufo",
      "roleEmoji": "",
      "command": line,
      "url": ""
    };
  });
  return commands;
}
function getAPIKey() {
  const storedAPIKey = localStorage.getItem('openaiAPIKey');
  if (storedAPIKey) {
    return storedAPIKey;
  } else {
    return '';
  }


}

function setAPIKey(key) {
  localStorage.setItem('openaiAPIKey', key);
}

function getIFTTTKey() {
  const storedAPIKey = localStorage.getItem('iftttKey');
  if (storedAPIKey) {
    return storedAPIKey;
  } else {
    const userInput = prompt('Please enter your IFTTT Key:');
    if (userInput) {
      localStorage.setItem('iftttKey', userInput);
      return userInput;
    } else {
      localStorage.setItem('', userInput);
      console.log('IFTTT Key is required for this IFTTT webhooks to work.');
      return '';
    }
  }
}

async function getEngines() {
  const apiKey = getAPIKey();

  const response = await axios.get('https://api.openai.com/v1/engines', {
    headers: {
      'Authorization': `Bearer ${apiKey}`
    }
  });

  return response.data; // return the list of available engines
}

async function uploadContentToOpenAI(fileName, content) {
  const currentDate = new Date();
  const formattedDate = currentDate.toISOString().slice(0, 19).replace(/[-T:]/g, '');
  if (!fileName) {
    fileName = `${formattedDate}.json`;
  }
  var messages = [{ "role": "system", "content": content }];

  const apiKey = await getAPIKey();
  const endpoint = 'https://api.openai.com/v1/files';
  const blob = new Blob([messages], { type: 'text/plain' });
  const file = new File([blob], fileName + '.json');
  const data = {
    purpose: "fine-tune",
    file: file
  };

  try {
    const response = await axios.post(endpoint, data, {
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'multipart/form-data'
      }
    });

    const fileId = response.data.id;
    return fileId;
  } catch (error) {
    console.error('Error:', error);
    return null;
  }
}

async function getTextContent(url, model, knowledge, setKnowledge) {
  var _ftext = '';
  try {
    console.log("get", url);
    const response = await fetch(url, { mode: 'no-cors' });
    const text = await response.text();
    console.log("get result", text);
    const _messages = [
      { role: "user", content: "page result text:" + text },
      { role: "user", content: "question:" + text + ". format in markdown." }
    ];
    var _p2 = {
      model: model,
      messages: _messages
    };

    const response2 = await openai.chat.completions.create(_p2);
    console.log("get markdown result", response2);
    if (response2) {
      _content = response2.choices[0]?.message?.content;
    }
    return _content;
  } catch (error) {
    console.error('Error:', error);
    return null;
  }
}
function getRandomEmoji() {
  const emojis = ["🦉", "🐝", "🦧"];
  const index = new Date().getMilliseconds() % emojis.length;
  return emojis[index];
}
function setStashKey(key,
  currentIndex,
  setContext,
  setKnowledge,
  setQuestion,
  setContent,
  setCurrentIndex,
  setCurrentKey,
  setTemperature,
  setShowTextarea) {
  const stashItem = pop(key);
  setCurrentKey(key);
  if (stashItem) {
    console.log(stashItem);
    if (stashItem.context) {
      setContext(stashItem.context);
    }
    if (stashItem.knowledge) {
      setKnowledge(stashItem.knowledge);
    }
    if (stashItem.question) {
      setQuestion(stashItem.question);
    }
    if (stashItem.content) {
      setContent(stashItem.content);
    }
    if (stashItem.temperature) {
      setTemperature(stashItem.temperature);
    }
    if (stashItem.showTextarea) {
      setShowTextarea(stashItem.showTextarea);
    }
  }
}

function setStashIndex(currentIndex,
  setContext,
  setKnowledge,
  setQuestion,
  setContent,
  setCurrentIndex,
  setCurrentKey,
  setTemperature,
  setShowTextarea) {
  var stashList = getStashList();
  var total = 0;
  if (stashList) {
    var _l = stashList.split(',');
    if (_l && Array.isArray(_l)) {
      total = _l.length;
      var key = _l[currentIndex];
      if (key) {
        console.log("shift+38:" + key);
        setStashKey(key,
          currentIndex,
          setContext,
          setKnowledge,
          setQuestion,
          setContent,
          setCurrentIndex,
          setCurrentKey,
          setTemperature,
          setShowTextarea);

      }
    }
  }
  return total;
}



async function askQuestion(text, model, context, knowledge, completionType, setContent, setContext, setMessage, content, temperature, filter, max_tokens, top_p, frequency_penalty, presence_penalty, scrollToBottom, performance, setPerformance, setThinking, currentKey, setSize, size) {
  const _messages = [
    { role: "user", content: "chat history:" + context },
    { role: "user", content: "knowledge:" + knowledge },
    { role: "user", content: "question:" + text + ". Use the content in knowledge and chat history to answer the question. It is for a project." }
  ];
  setThinking(getRandomEmoji());
  var _content = '';
  var _c = '';
  var _finish_reason = '';
  var calculator = new PerformanceCalculator();
  calculator.start();

  // handle open ai test completions
  const handleRestCompletion = async () => {
    var _p2 = {
      model: model,
      messages: _messages,
      temperature: temperature,
      top_p: top_p,
      frequency_penalty: frequency_penalty,
      presence_penalty: presence_penalty
    };
    if (max_tokens > 0) {
      _p2.max_tokens = max_tokens;
    }
    console.debug(_p2);
    const response = await openai.chat.completions.create(_p2);
    if (response) {
      _content = response.choices[0]?.message?.content;
      _finish_reason = response.choices[0]?.finish_reason;
      setMessage(_finish_reason);
      var _c = [
        ...content,
        FormatService.getMessageWithTimestamp(text, 'user'),
        FormatService.getMessageWithTimestamp(_content, 'assistant')
      ];
      setContent(_c);
      var _tokens = response.usage?.completion_tokens + '+' + response.usage?.prompt_tokens + '=' + response.usage?.total_tokens;
      stash(currentKey, context, knowledge, text, _c);

    }
    return response;
  }

  // handle open ai stream completions
  const handleStreamCompletion = async () => {
    var _p = {
      model: model,
      messages: _messages,
      stream: true,
      temperature: temperature,
      top_p: top_p,
      frequency_penalty: frequency_penalty,
      presence_penalty: presence_penalty
    };

    console.debug(_p);
    const stream = await openai.beta.chat.completions.stream(_p);
    if (stream) {
      for await (const chunk of stream) {
        setThinking(getRandomEmoji());
        var _d = chunk.choices[0]?.delta;
        var _temp = chunk.choices[0]?.delta?.content || '';
        _c = _c + _temp;
        setContent([
          ...content,
          FormatService.getMessageWithTimestamp(text, 'user'),
          FormatService.getMessageWithTimestamp(_c, 'assistant')
        ]);
      }

      const response = await stream.finalChatCompletion();
      _content = response.choices[0]?.message?.content;
      _finish_reason = response.choices[0]?.finish_reason;
      setMessage(_finish_reason);
      var _cc = [
        ...content,
        FormatService.getMessageWithTimestamp(text, 'user'),
        FormatService.getMessageWithTimestamp(_content, 'assistant')
      ];
      setContent(_cc);
      var _tokens = response.usage?.completion_tokens + '+' + response.usage?.prompt_tokens + '=' + response.usage?.total_tokens;
      stash(currentKey, context, knowledge, text, _cc);


    }
    return;
  }

  // hanlde open ai dall-e-3 completions
  const handleDalliRestCompletion = async () => {
    const _daliprompt = "chat history:" + context + "knowledge:" + knowledge + "question:" + text;
    var p3 = {
      model: "dall-e-3",
      prompt: _daliprompt,
      size: size,
      quality: "standard",
      n: 1
    };

    const response3 = await openai.images.generate(p3);
    console.debug('handleDalliRestCompletion', p3);
    if (response3) {
      var image_url = response3.data[0].url;
      _content = image_url
      setMessage("image");
      var _c = [
        ...content,
        FormatService.getMessageWithTimestamp(text, 'user'),
        FormatService.getMessageWithTimestamp(_content, 'image')
      ];
      setContent(_c);
      stash(currentKey, context, knowledge, text, _c);

    }
    return response3;
  }

  //
  try {
    let response;
    if (model === 'dall-e-3') {
      response = await handleDalliRestCompletion();
    } else if (completionType === 'rest') {
      response = await handleRestCompletion();
    } else if (completionType === 'stream') {
      await handleStreamCompletion();
    }

    return response;
  } catch (error) {
    throw error;
    console.error("Error sending message to OpenAI: ", error);
  } finally {
    calculator.end();
    var duration = calculator.calculateDuration();
    setPerformance(duration);

    scrollToBottom();
  }
}

// Function to generate a message with a timestamp

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

function formatJSONToString(jsonObject) {
  let formattedString = '';
  for (const key in jsonObject) {
    if (jsonObject.hasOwnProperty(key)) {
      formattedString += `${key}: ${JSON.stringify(jsonObject[key])}\n`;
    }
  }
  return formattedString;
}

function getTooBigEmoji(_totalChars, maxChars) {
  if (_totalChars >= maxChars) {
    return '🐋'; // Dinosaur emoji for the biggest level
  } else if (_totalChars >= (maxChars * 0.75)) {
    return '🦕'; // Bear emoji for the third level
  } else if (_totalChars >= (maxChars * 0.5)) {
    return '🐘'; // Lion emoji for the second level
  } else if (_totalChars >= (maxChars * 0.25)) {
    return '🐁'; // Mouse emoji for the first level
  }
}
// Function to save content in local storage
function stash(key, context, knowledge, question, content, temperature, showTextarea) {
  const stashKey = "stash-" + key;
  const _c = {
    context: context,
    key: key,
    knowledge: knowledge,
    question: question,
    content: content,
    temperature: temperature,
    showTextarea: showTextarea,
    timestamp: new Date().toISOString()
  };

  localStorage.setItem(stashKey, JSON.stringify(_c));
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


function getStashList() {
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
async function getUploadedFiles() {
  const apiKey = getAPIKey();
  const endpoint = 'https://api.openai.com/v1/files';

  try {
    const response = await axios.get(endpoint, {
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });

    const files = response.data;
    return files;
  } catch (error) {
    console.error('Error:', error);
    return null;
  }
}
export default {
  getAPIKey,
  setAPIKey,
  askQuestion,
  getMessageWithTimestamp,
  getVerb,
  getStashList,
  pop,
  stash,
  formatJSONToString,
  getTooBigEmoji,
  getRandomEmoji,
  getTextContent,
  handleImport,
  handleExport,
  setStashIndex,
  getHelp,
  getCommands,
  getSettings,
  getIndicators,
  getUFO,
  save,
  getOptions,
  getFormattedCommands,
  calculateTokens,
  getEngines,
  uploadContentToOpenAI,
  getUploadedFiles,
  setStashKey
};