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
      setKnowledge(text);
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
      setContent([
        ...content,
        FormatService.getMessageWithTimestamp(text, 'user'),
        FormatService.getMessageWithTimestamp(_content, 'assistant')
      ]);
      var _tokens = response.usage?.completion_tokens + '+' + response.usage?.prompt_tokens + '=' + response.usage?.total_tokens;
      setTokens(_tokens);
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
      setContent([
        ...content,
        FormatService.getMessageWithTimestamp(text, 'user'),
        FormatService.getMessageWithTimestamp(_content, 'assistant')
      ]);
      var _tokens = response.usage?.completion_tokens + '+' + response.usage?.prompt_tokens + '=' + response.usage?.total_tokens;
      setTokens(_tokens);
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

export default {
  sendMessageToOpenAI,
  getMessageWithTimestamp,
  getVerb,
  stashList,
  pop,
  stash,
  formatJSONToString,
  getTooBigEmoji,
  getRandomEmoji,
  getTextContent,
  handleImport,
  handleExport
};