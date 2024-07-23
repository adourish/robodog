
import { FormatService } from './FormatService';
import { ConsoleService } from './ConsoleService';
const formatService = new FormatService();
const consoleService = new ConsoleService();
const duckduckgoSearch = require("duckduckgo-search");

class SearchService {
  constructor() {
    console.debug('SearchService init')
  }
  setAPIKey(key) {
    console.debug('Set rapidapiAPIKey', key)
    localStorage.setItem('rapidapiAPIKey', key);
  }
  async getAPIKeyAsync() {
    const storedAPIKey = await localStorage.getItem('rapidapiAPIKey');
    console.debug('Get rapidapiAPIKey', storedAPIKey)
    if (storedAPIKey) {
      return storedAPIKey;
    } else {
      return '';
    }
  }

  getAPIKey() {
    const storedAPIKey = localStorage.getItem('openaiAPIKey');
    console.debug('Get rapidapiAPIKey', storedAPIKey)
    if (storedAPIKey) {
      return storedAPIKey;
    } else {
      return '';
    }
  }

  async setAPIKeyAsync(key) {
    console.debug('Set rapidapiAPIKey', key)
    await localStorage.setItem('rapidapiAPIKey', key);
  }

  search(text, setThinking, setMessage, setContent, content) {
    const encodedText = encodeURIComponent(text);
    const apiUrl = `https://google-search74.p.rapidapi.com/?query=${encodedText}&limit=10&related_keywords=true`;
    var updatedContent = [];
    setThinking(formatService.getRandomEmoji());
    
    const xhr = new XMLHttpRequest();
    xhr.withCredentials = true;

    xhr.addEventListener('readystatechange', function () {
      if (this.readyState === this.DONE) {
        const data = JSON.parse(this.responseText);
    console.log(data);

    // Extract data from the knowledge panel
    const knowledge = data.knowledge_panel;
    const name = knowledge.name;
    const description = knowledge.description.text;
    const info = knowledge.info.map(i => `${i.title}: ${i.labels.join(", ")}`).join("\n");
    var assistantText = `Name: ${name}\nDescription: ${description}\nInfo:\n${info}`;

    const formattedUserMessage = formatService.getMessageWithTimestamp(text, 'user');
    const formattedAssistantMessage = formatService.getMessageWithTimestamp(assistantText, 'search');
   
        updatedContent = [
          ...content,
          formattedUserMessage,
          formattedAssistantMessage
        ];
        for (let i = 0; i < data.results.length; i++) {
          const result = data.results[i];
          assistantText = `\n${result.title} - ${result.description}`;
          const formattedAssistantMessageResults = formatService.getMessageWithTimestamp(assistantText, 'search', result.url);
          updatedContent.push(formattedAssistantMessageResults)
        }

        setContent(updatedContent);
      }
    });

    xhr.open('GET', apiUrl);
    xhr.setRequestHeader('x-rapidapi-key', 'a0d887c79fmsh480840c77fc09acp1ed16cjsn043378f4f54d'); // Replace 'Your-RapidAPI-Key' with your actual key
    xhr.setRequestHeader('x-rapidapi-host', 'google-search74.p.rapidapi.com');

    xhr.send(null);
    return updatedContent;
  }
}


export { SearchService };