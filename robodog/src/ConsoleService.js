import OpenAI from 'openai';
import { PerformanceCalculator} from './PerformanceCalculator';
const openai = new OpenAI({
  apiKey: getAPIKey(),
  dangerouslyAllowBrowser: true,
});


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
        getMessageWithTimestamp(text, 'user'),
        getMessageWithTimestamp(_content, 'assistant')
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
          getMessageWithTimestamp(text, 'user'),
          getMessageWithTimestamp(_c, 'assistant')
        ]);
      }

      const response = await stream.finalChatCompletion();
      _content = response.choices[0]?.message?.content;
      _finish_reason = response.choices[0]?.finish_reason;
      setMessage(_finish_reason);
      setContent([
        ...content,
        getMessageWithTimestamp(text, 'user'),
        getMessageWithTimestamp(_content, 'assistant')
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
  getRandomEmoji
};