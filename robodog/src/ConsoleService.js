import OpenAI from 'openai';
import { PerformanceCalculator } from './PerformanceCalculator';
import FormatService from './FormatService';
import FileService from './FileService';
const openai = new OpenAI({
  apiKey: getAPIKey(),
  dangerouslyAllowBrowser: true,
});

function getMessageWithTimestamp(command, role) {
  var s = FormatService.getMessageWithTimestamp(command, role);
  return s;
}

function handleExport(fileName, knowledge, content) {
  const currentDate = new Date();
  const formattedDate = currentDate.toISOString().slice(0, 19).replace(/[-T:]/g, '');
  if (!fileName) {
    fileName = `${formattedDate}.txt`;
  }

  const fileContent = knowledge + '\n\n' + content.map(item => item.message).join('\n\n');

  const element = document.createElement('a');
  element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(fileContent));
  element.setAttribute('download', fileName);
  element.style.display = 'none';
  document.body.appendChild(element);
  element.click();
  document.body.removeChild(element);
}


function handleImport(setKnowledge, knowledge, setContent, content) {
  console.log("handleUpload")
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
  return settings;
}

function getCommands() {
  var commands = ['commands: ',
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
    ' SHIFT+UP - cycle through stash list.'];
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
  return indicators;

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

function setStashIndex(currentIndex,
  setContext,
  setKnowledge,
  setInputText,
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
        console.log("shift+38");
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
            setInputText(stashItem.question);
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
    }
  }
  return total;
}

async function sendMessageToOpenAI(text, model, context, knowledge, completionType, setContent, setContext, setMessage, content, setTokens, temperature, filter, max_tokens, top_p, frequency_penalty, presence_penalty, scrollToBottom, performance, setPerformance, setThinking) {
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
    console.log(_p2);
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
      setTokens(_tokens);
      stash("autosave", context, knowledge, text, _c);
    }
    return response;
  }



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

    console.log(_p);
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
      setTokens(_tokens);
      stash("autosave", context, knowledge, text, _cc);
      console.log(_tokens);
      console.log(response);
    }
    return;
  }

  try {
    let response;

    if (completionType === 'rest') {
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

export default {
  sendMessageToOpenAI,
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
  getIndicators
};