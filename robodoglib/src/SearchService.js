
import { FormatService } from './FormatService';
import { ConsoleService } from './ConsoleService';
import { ProviderService } from './ProviderService';
const formatService = new FormatService();
const consoleService = new ConsoleService();
const providerService = new ProviderService();

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
    const storedAPIKey = localStorage.getItem('rapidapiAPIKey');
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
    try {
        const encodedText = encodeURIComponent(text);
        var config = providerService.getJson();
        var _model = providerService.getModel('search');
        var _provider = providerService.getProvider(_model.provider)
        var _baseUrl = _provider.baseUrl;
        var _apiKey = _provider.apiKey;
        console.log('askQuestion', _provider, _model)
        const apiUrl = _baseUrl + `/?query=${encodedText}&limit=10&related_keywords=true`;
        var updatedContent = [];
        setThinking(formatService.getRandomEmoji());
        
        const xhr = new XMLHttpRequest();
        xhr.withCredentials = true;

        xhr.addEventListener('readystatechange', function () {
            if (this.readyState === this.DONE) {
                if (this.status >= 200 && this.status < 400) {
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
                } else {
                    const errorMessage = "An error occurred while fetching data from the server.";
                    setMessage(errorMessage);
                    console.error(errorMessage);
                }
            }
        });

        xhr.addEventListener('error', function() {
            const errorMessage = "An error occurred during the request. Please try again later.";
            setMessage(errorMessage);
            console.error(errorMessage);
        });

        xhr.open('GET', apiUrl);
        xhr.setRequestHeader('x-rapidapi-key', _apiKey); 
        xhr.setRequestHeader('x-rapidapi-host', 'google-search74.p.rapidapi.com');

        xhr.send(null);
        return updatedContent;
    } catch (error) {
        const errorMessage = "An error occurred while processing the request.";
        setMessage(errorMessage);
        console.error(error);
    } finally {
        // Perform any cleanup or final actions here
    }
}

}


export { SearchService };