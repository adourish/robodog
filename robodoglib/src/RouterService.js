import OpenAI from 'openai';
import LlamaAI from 'llamaai';
import axios from 'axios';
import { PerformanceCalculator } from './PerformanceCalculator';
import { FormatService } from './FormatService';
import { ConsoleService } from './ConsoleService';
import { SearchService } from './SearchService';
import { ProviderService } from './ProviderService';
const formatService = new FormatService();
const consoleService = new ConsoleService();
const searchService = new SearchService();
const providerService = new ProviderService();
class RouterService {
  constructor() {
    console.debug('RouterService init')
  }


  setAPIKey(key) {
    console.debug('Set openaiAPIKey', key)
    localStorage.setItem('openaiAPIKey', key);
  }
  async getAPIKeyAsync() {
    const storedAPIKey = await localStorage.getItem('openaiAPIKey');
    console.debug('Get openaiAPIKey', storedAPIKey)
    if (storedAPIKey) {
      return storedAPIKey;
    } else {
      return '';
    }
  }

  async setAPIKeyAsync(key) {
    console.debug('Set openaiAPIKey', key)
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

  getLlamaAI(model) {
    var _model = providerService.getModel(model);
    var _provider = providerService.getProvider(_model.provider)
    var _apiKey = _provider.apiKey;
    var _baseUrl = _provider.baseUrl;
    console.log(_model, _provider)
    var _c = {
      apiKey: _apiKey,
      dangerouslyAllowBrowser: true
    }

    const llamaAI = new LlamaAI(_apiKey, _baseUrl);
    console.log(llamaAI)
    return llamaAI;


  }
  getOpenAI(model) {
    var _model = providerService.getModel(model);
    var _provider = providerService.getProvider(_model.provider)
    var _apiKey = _provider.apiKey;
    var _baseUrl = _provider.baseUrl;
    console.log(_model, _provider)
    var _c = {
      apiKey: _apiKey,
      dangerouslyAllowBrowser: true
    }
    const openai = new OpenAI(_c);
    console.log(openai);
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
    const openai = this.getOpenAI(model);
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
      return _cc;
    }
  }

  async handleLlamaRestCompletion(model,
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
    const openai = this.getLlamaAI(model);
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
      return _cc;
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
    const openai = this.getOpenAI(model);
    console.log(openai)
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
    return _cc;
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
    const openai = this.getOpenAI(model);
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
    return _c;
  }

  async askQuestion(text,
    model,
    search,
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
    presence_penalty, scrollToBottom, performance, setPerformance, setThinking, currentKey, setSize, size) {


    console.log(config)
    const messages = [
      { role: "user", content: "chat history:" + context },
      { role: "user", content: "knowledge:" + knowledge },
      { role: "user", content: "question:" + text + "If available. Use the content in knowledge and chat history to answer the question." }
    ];
    setThinking(formatService.getRandomEmoji());
    var calculator = new PerformanceCalculator();
    calculator.start();
    var _cc = []
    try {
      var config = providerService.getJson();
      var _model = providerService.getModel(model);
      var _provider = providerService.getProvider(_model.provider)
      console.log('askQuestion', _provider, _model)
      if (_model && _model.provider && _provider && _provider.provider) {
        if (model === 'dall-e-3') {
          console.log('rounter handleDalliRestCompletion')
          _cc = await this.handleDalliRestCompletion(model,
            messages,
            temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
            setThinking, setContent, setMessage, content, text, currentKey, context, knowledge, size);
        } else if (model === 'search') {
          console.log('rounter search')
          _cc = await searchService.search(text, setThinking, setMessage, setContent, content);

        } else if (_model.provider === 'openAI' && _model.stream === true) {
          console.log('rounter openAI handleStreamCompletion')
          _cc = await this.handleStreamCompletion(model,
            messages,
            temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
            setThinking, setContent, setMessage, content, text, currentKey, context, knowledge);
        } else if (_model.provider === 'openAI' && _model.stream === false) {
          console.log('rounter openAI handleRestCompletion')
          _cc = await this.handleRestCompletion(model,
            messages,
            temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
            setThinking, setContent, setMessage, content, text, currentKey, context, knowledge);
        } else if (_model.provider === 'llamaAI' && _model.stream === false) {
          console.log('rounter openAI handleRestCompletion')
          _cc = await this.handleLlamaRestCompletion(model,
            messages,
            temperature, top_p, frequency_penalty, presence_penalty, max_tokens,
            setThinking, setContent, setMessage, content, text, currentKey, context, knowledge);
        } else {
          console.log('no matching model condigtions');
        }

      } else {
        console.log('no matching provider or model');
      }

    } catch (error) {
      console.error("Error sending message to OpenAI: ", error);
      throw error;
    } finally {
      calculator.end();
      var duration = calculator.calculateDuration();
      setPerformance(duration);
      scrollToBottom();
    }
    return _cc;
  }

}

export { RouterService };