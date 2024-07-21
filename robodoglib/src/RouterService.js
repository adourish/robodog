import OpenAI from 'openai';
import axios from 'axios';
import { PerformanceCalculator } from './PerformanceCalculator';
import { FormatService } from './FormatService';
import { ConsoleService } from './ConsoleService';
import { SearchService } from './SearchService';
const formatService = new FormatService();
const consoleService = new ConsoleService();
const searchService = new SearchService();
class RouterService {
  constructor() {
    console.debug('RouterService init')
  }


  setAPIKey(key) {
    console.debug('setAPIKey', key)
    localStorage.setItem('openaiAPIKey', key);
  }
  async getAPIKeyAsync() {
    const storedAPIKey = await localStorage.getItem('openaiAPIKey');
    console.debug('getAPIKey', storedAPIKey)
    if (storedAPIKey) {
      return storedAPIKey;
    } else {
      return '';
    }
  }

  async setAPIKeyAsync(key) {
    console.debug('setAPIKey', key)
    await localStorage.setItem('openaiAPIKey', key);
  }
  async getEngines() {
    const apiKey = await this.getAPIKeyAsync();

    const response = await axios.get('https://api.openai.com/v1/engines', {
      headers: {
        'Authorization': `Bearer ${apiKey}`
      }
    });

    return response.data; // return the list of available engines
  }


  getOpenAI() {
    const openai = new OpenAI({
      apiKey: this.getAPIKey(),
      dangerouslyAllowBrowser: true,
    });
    return openai;
  }

  getAPIKey() {
    const storedAPIKey = localStorage.getItem('openaiAPIKey');
    console.debug('getAPIKey', storedAPIKey)
    if (storedAPIKey) {
      return storedAPIKey;
    } else {
      return '';
    }
  }

  async handleRestCompletion(model,
    messages,
    temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
    setThinking, setContent, setMessage, content, text, currentKey, context, knowledge
  ) {
    var _p2 = {
      model: model,
      messages: messages,
      temperature: temperature,
      top_p: top_p,
      frequency_penalty: frequency_penalty,
      presence_penalty: presence_penalty
    };
    var _r = { "content": null, "finish_reason": null, "text": null }
    if (max_tokens > 0) {
      _p2.max_tokens = max_tokens;
    }
    console.debug(_p2);
    const openai = this.getOpenAI();
    const response = await openai.chat.completions.create(_p2);
    if (response) {
      var _content = response.choices[0]?.message?.content;
      var _finish_reason = response.choices[0]?.finish_reason;
      _r.content = _content
      _r.finish_reason = _finish_reason;
      setMessage(_finish_reason);
      var _cc = [
        ...content,
        FormatService.getMessageWithTimestamp(text, 'user'),
        FormatService.getMessageWithTimestamp(_content, 'assistant')
      ];
      setContent(_cc);
      consoleService.stash(currentKey, context, knowledge, text, _cc);
    }
  }

  // handle open ai stream completions
  async handleStreamCompletion(model,
    messages,
    temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
    setThinking, setContent, setMessage, content, text, currentKey, context, knowledge) {
    var _p = {
      model: model,
      messages: messages,
      stream: true,
      temperature: temperature,
      top_p: top_p,
      frequency_penalty: frequency_penalty,
      presence_penalty: presence_penalty
    };
    var _c = '';
    var _r = { "content": null, "finish_reason": null, "text": null }
    console.debug(_p);
    const openai = this.getOpenAI();
    const stream = openai.beta.chat.completions.stream(_p);
    if (stream) {
      for await (const chunk of stream) {
        setThinking(formatService.getRandomEmoji());
        var _temp = chunk.choices[0]?.delta?.content || '';
        _c = _c + _temp;
        setContent([
          ...content,
          formatService.getMessageWithTimestamp(text, 'user'),
          formatService.getMessageWithTimestamp(_c, 'assistant')
        ]);
      }

      const response = await stream.finalChatCompletion();
      var _content = response.choices[0]?.message?.content;
      var _finish_reason = response.choices[0]?.finish_reason;
      _r.content = _content
      _r.finish_reason = _finish_reason;
      setMessage(_finish_reason);
      var _cc = [
        ...content,
        formatService.getMessageWithTimestamp(text, 'user'),
        formatService.getMessageWithTimestamp(_content, 'assistant')
      ];
      setContent(_cc);
      consoleService.stash(currentKey, context, knowledge, text, _cc);

    }
    return _r;
  }

  // hanlde open ai dall-e-3 completions
  async handleDalliRestCompletion(model,
    messages,
    temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
    setThinking, setContent, setMessage, content, text, currentKey, context, knowledge, size) {
    const _daliprompt = "chat history:" + context + "knowledge:" + knowledge + "question:" + text;
    var p3 = {
      model: "dall-e-3",
      prompt: _daliprompt,
      size: size,
      quality: "standard",
      n: 1
    };
    const openai = this.getOpenAI();
    const response3 = await openai.images.generate(p3);
    console.debug('handleDalliRestCompletion', p3);
    if (response3) {
      var image_url = response3.data[0].url;
      var _content = image_url
      setMessage("image");
      var _c = [
        ...content,
        formatService.getMessageWithTimestamp(text, 'user'),
        formatService.getMessageWithTimestamp(_content, 'image')
      ];
      setContent(_c);
      consoleService.stash(currentKey, context, knowledge, text, _c);

    }
    return response3;
  }

  async askQuestion(text, model, context, knowledge, completionType, setContent, setContext, setMessage, content, temperature, filter, max_tokens, top_p, frequency_penalty, presence_penalty, scrollToBottom, performance, setPerformance, setThinking, currentKey, setSize, size) {
    const messages = [
      { role: "user", content: "chat history:" + context },
      { role: "user", content: "knowledge:" + knowledge },
      { role: "user", content: "question:" + text + "If available. Use the content in knowledge and chat history to answer the question." }
    ];
    setThinking(formatService.getRandomEmoji());
    var calculator = new PerformanceCalculator();
    calculator.start();

    try {
      let response;
      if (model === 'dall-e-3') {
        response = await this.handleDalliRestCompletion(model,
          messages,
          temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
          setThinking, setContent, setMessage, content, text, currentKey, context, knowledge, size);
      } else if (model === 'search') {
        response = await searchService.search(text, setThinking, setMessage, setContent, content);

      } else if (completionType === 'rest') {
        response = await this.handleRestCompletion(model,
          messages,
          temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
          setThinking, setContent, setMessage, content, text, currentKey, context, knowledge);
      } else if (completionType === 'stream') {
        response = await this.handleStreamCompletion(model,
          messages,
          temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
          setThinking, setContent, setMessage, content, text, currentKey, context, knowledge);
      }

      return response;
    } catch (error) {
      console.error("Error sending message to OpenAI: ", error);
      throw error;
    } finally {
      calculator.end();
      var duration = calculator.calculateDuration();
      setPerformance(duration);
      scrollToBottom();
    }
  }

}

export { RouterService };