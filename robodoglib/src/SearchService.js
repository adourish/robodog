
import { FormatService } from './FormatService';
import { ConsoleService } from './ConsoleService';
const formatService = new FormatService();
const consoleService = new ConsoleService();
import duckDuckGoSearch from 'duckduckgo-search'

class SearchService {
  constructor() {
    console.debug('SearchService init')
  }
  
  async search(text, setThinking, setMessage, setContent, content) {
    try {
      setThinking(formatService.getRandomEmoji());
      var searchResult = '';
      const result = await duckDuckGoSearch.text(text); // Use the correct method to make the search request
      console.log(result);
      
      if (!result || result.length === 0) {
        throw new Error('No results found');
      }else{
        searchResult = result[0].text;
      }

      // Assuming the result is an array and each item has a `text` property
      setMessage(searchResult);
      
      const formattedUserMessage = formatService.getMessageWithTimestamp(text, 'user');
      const formattedAssistantMessage = formatService.getMessageWithTimestamp(searchResult, 'assistant');
      
      var updatedContent = [
        ...content,
        formattedUserMessage,
        formattedAssistantMessage
      ];
      setContent(updatedContent);

      return result; // Return the search result
    } catch (error) {
      console.error('Error fetching search results:', error);
      return null;
    }
  }
}

export { SearchService };