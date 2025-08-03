import OpenAI from "openai";
import LlamaAI from "llamaai";
import axios from "axios";
import { PerformanceCalculator } from "./PerformanceCalculator";
import { FormatService } from "./FormatService";
import { ConsoleService } from "./ConsoleService";
import { SearchService } from "./SearchService";
import { ProviderService } from "./ProviderService";
import { RouterModel } from "./RouterModel";
const formatService = new FormatService();
const consoleService = new ConsoleService();
const searchService = new SearchService();
const providerService = new ProviderService();
class RouterService {
  constructor() {
    console.debug("RouterService init");
  }


  getOpenAI(model) {
    const _model = providerService.getModel(model);
    const _provider = providerService.getProvider(_model.provider);
    const _apiKey = _provider.apiKey;
    const _baseUrl = _provider.baseUrl; // e.g. “https://adourish.github.io

    let _httpReferer = _provider.httpReferer;
    if (!_httpReferer || _httpReferer.trim() === '') {
        _httpReferer = this.getRefererUrl(); // Use the referer from getRefererUrl if _httpReferer is empty or null
    }

    console.log(_model, _provider);
    const clientConfig = {
        apiKey: _apiKey,
        baseURL: _baseUrl,
        dangerouslyAllowBrowser: true,
        extraHeaders: {
            "HTTP-Referer": _httpReferer, 
        },
    };

    const openai = new OpenAI(clientConfig);
    console.log(openai);
    return openai;
}

  getRefererUrl() {
    // If this is running on Android webview, you might pass this from the Android side.
    return document.referrer || 'https://adourish.github.io';  // Use a default if none
}

  async handleRestCompletion(
    model,
    messages,
    temperature,
    top_p,
    frequency_penalty,
    presence_penalty,
    max_tokens,
    setThinking,
    setContent,
    setMessage,
    content,
    text,
    currentKey,
    context,
    knowledge
  ) {
    var _p2 = {
      model: model,
      messages: messages,
      temperature: temperature,
      top_p: top_p,
      frequency_penalty: frequency_penalty,
      presence_penalty: presence_penalty,
    };
    var _r = { content: null, finish_reason: null, text: null };
    if (max_tokens > 0) {
      _p2.max_tokens = max_tokens;
    }
    console.debug(_p2);
    const openai = this.getOpenAI(model);
    try {
      const response = await openai.chat.completions.create(_p2);
      if (response) {
        var _content = response.choices[0]?.message?.content;
        var _finish_reason = response.choices[0]?.finish_reason;
        _r.content = _content || "No content available";
        _r.finish_reason = _finish_reason || "No finish reason";
        setMessage(_finish_reason);
        var _cc = [
          ...content,
          FormatService.getMessageWithTimestamp(text, "user"),
          FormatService.getMessageWithTimestamp(_content, "assistant"),
        ];
        setContent(_cc);
        consoleService.stash(currentKey, context, knowledge, text, _cc);
        return _cc;
      }
    } catch (error) {
      console.error("Error:", error);
      return { error: "An error occurred while processing the request." };
    }
    return null;
  }


  // handle open ai stream completions
  async handleStreamCompletion(
    model,
    messages,
    temperature,
    top_p,
    frequency_penalty,
    presence_penalty,
    max_tokens,
    setThinking,
    setContent,
    setMessage,
    content,
    text,
    currentKey,
    context,
    knowledge
  ) {
    var _p = {
      model: model,
      messages: messages,
      stream: true,
      temperature: temperature,
      top_p: top_p,
      frequency_penalty: frequency_penalty,
      presence_penalty: presence_penalty,
    };
    const refererUrl = this.getRefererUrl();
    var _c = "";
    var _r = { content: null, finish_reason: null, text: null };
    console.debug(_p);
    try {
      const openai = this.getOpenAI(model);
      console.log(openai);
      const stream = openai.beta.chat.completions.stream(_p);
      if (stream) {
        for await (const chunk of stream) {
          setThinking(formatService.getRandomEmoji());
          var _temp = chunk.choices[0]?.delta?.content || "";
          _c = _c + _temp;
          setContent([
            ...content,
            formatService.getMessageWithTimestamp(text, "user"),
            formatService.getMessageWithTimestamp(_c, "assistant"),
          ]);
          consoleService.scrollToBottom();
        }

        const response = await stream.finalChatCompletion();
        var _content = response.choices[0]?.message?.content;
        var _finish_reason = response.choices[0]?.finish_reason;
        _r.content = _content;
        _r.finish_reason = _finish_reason;
        setMessage(_finish_reason);
        var _cc = [
          ...content,
          formatService.getMessageWithTimestamp(text, "user"),
          formatService.getMessageWithTimestamp(_content, "assistant"),
        ];
        setContent(_cc);

        consoleService.stash(currentKey, context, knowledge, text, _cc);
      }
      return _cc || content; // ensure a return value is always returned
    } catch (ex) {
      const errorMessage = `Error occurred: ${ex.message}, Referer URL: ${refererUrl}, Stack: ${ex.stack}`;
      console.error(ex);
      var _ee = [
        ...content,
        formatService.getMessageWithTimestamp(errorMessage, "error"),
      ];
      setContent(_ee);
      return content; // return existing content in case of error
    }
  }
  // hanlde open ai dall-e-3 completions
  async handleDalliRestCompletion(
    model,
    messages,
    temperature,
    top_p,
    frequency_penalty,
    presence_penalty,
    max_tokens,
    setThinking,
    setContent,
    setMessage,
    content,
    text,
    currentKey,
    context,
    knowledge,
    size
  ) {
    let _c = [];
    try {
      const _daliprompt =
        "chat history:" +
        context +
        "knowledge:" +
        knowledge +
        "question:" +
        text;
      var p3 = {
        model: "dall-e-3",
        prompt: _daliprompt,
        size: size,
        quality: "standard",
        n: 1,
      };
      const openai = this.getOpenAI(model);
      const response3 = await openai.images.generate(p3);
      console.debug("handleDalliRestCompletion", p3);
      if (response3) {
        var image_url = response3.data[0].url;
        var _content = image_url;
        setMessage("image");
        _c = [
          ...content,
          formatService.getMessageWithTimestamp(text, "user"),
          formatService.getMessageWithTimestamp(_content, "image"),
        ];
        setContent(_c);
        consoleService.stash(currentKey, context, knowledge, text, _c);
      }
    } catch (err) {
      console.error("Error in handleDalliRestCompletion:", err);
      _c = [
        ...content,
        formatService.getMessageWithTimestamp(
          "Sorry, something went wrong.",
          "bot"
        ),
      ];
      setContent(_c);
    }
    return _c;
  }

  async routeQuestion(routerModel) {
    var _cc = this.askQuestion(
      routerModel.question,
      routerModel.model,
      routerModel.context,
      routerModel.knowledge,
      routerModel.setContent,
      routerModel.setMessage,
      routerModel.content,
      routerModel.temperature,
      routerModel.max_tokens,
      routerModel.top_p,
      routerModel.frequency_penalty,
      routerModel.presence_penalty,
      routerModel.setPerformance,
      routerModel.setThinking,
      routerModel.currentKey,
      routerModel.size
    );
    routerModel.content = _cc;
    return routerModel;
  }

  async askQuestion(
    text,
    model,
    context,
    knowledge,
    setContent,
    setMessage,
    content,
    temperature,
    max_tokens,
    top_p,
    frequency_penalty,
    presence_penalty,
    setPerformance,
    setThinking,
    currentKey,
    size,
    scrollToBottom
  ) {
    console.log(config);

    let systemRole = "system";
    if (model === "o1-mini" || model === "o1") {
      systemRole = "user";
    }
    const messages = [
      { role: "user", content: "Chat History:" + context },
      { role: "user", content: "knowledge Base:" + knowledge },
      { role: "user", content: "Question:" + text },
      {
        role: systemRole,
        content:
          "Instruction 1: Analyze the provided 'Chat History:' and 'Knowledge Base:' to understand and answer the user's 'Question:' Do not provide answers based solely on the chat history or context.",
      }
    ];

    setThinking(formatService.getRandomEmoji());
    var calculator = new PerformanceCalculator();
    calculator.start();
    var _cc = [];
    try {
      var config = providerService.getJson();
      var _model = providerService.getModel(model);
      var _provider = providerService.getProvider(_model.provider);
      console.log("askQuestion", _provider, _model);
      if (_model && _model.provider && _provider && _provider.provider) {
        if (model === "dall-e-3") {
          console.log("rounter handleDalliRestCompletion");
          _cc = await this.handleDalliRestCompletion(
            model,
            messages,
            temperature,
            top_p,
            frequency_penalty,
            presence_penalty,
            max_tokens,
            setThinking,
            setContent,
            setMessage,
            content,
            text,
            currentKey,
            context,
            knowledge,
            size
          );
        } else if (model === "search") {
          console.log("rounter search");
          _cc = await searchService.search(
            text,
            setThinking,
            setMessage,
            setContent,
            content
          );
        } else if (_model.provider === "openAI" && _model.stream === true) {
          console.log("rounter openAI handleStreamCompletion");
          _cc = await this.handleStreamCompletion(
            model,
            messages,
            temperature,
            top_p,
            frequency_penalty,
            presence_penalty,
            max_tokens,
            setThinking,
            setContent,
            setMessage,
            content,
            text,
            currentKey,
            context,
            knowledge
          );
        } else if (_model.provider === "openRouter" && _model.stream === true) {
          console.log("rounter openRouter handleStreamCompletion");
          _cc = await this.handleStreamCompletion(
            model,
            messages,
            temperature,
            top_p,
            frequency_penalty,
            presence_penalty,
            max_tokens,
            setThinking,
            setContent,
            setMessage,
            content,
            text,
            currentKey,
            context,
            knowledge
          );
        } else if (_model.provider === "openAI" && _model.stream === false) {
          console.log("rounter openAI handleRestCompletion");
          _cc = await this.handleRestCompletion(
            model,
            messages,
            temperature,
            top_p,
            frequency_penalty,
            presence_penalty,
            max_tokens,
            setThinking,
            setContent,
            setMessage,
            content,
            text,
            currentKey,
            context,
            knowledge
          );
        } else if (_model.stream === true) {
          console.log("rounter openAI handleRestCompletion");
          console.log("rounter fall through " +_model.provider + " handleStreamCompletion");
          _cc = await this.handleStreamCompletion(
            model,
            messages,
            temperature,
            top_p,
            frequency_penalty,
            presence_penalty,
            max_tokens,
            setThinking,
            setContent,
            setMessage,
            content,
            text,
            currentKey,
            context,
            knowledge
          );
        } else {
          console.log("no matching model condigtions");
        }
      } else {
        console.log("no matching provider or model");
      }
      setThinking('🦥');
    } catch (error) {
      setThinking('🐛');
      console.error("Error sending message to provider: ", error);
      setMessage("Error sending message to provider: " + error);
      throw error;
    } finally {
      calculator.end();
      var duration = calculator.calculateDuration();
      setPerformance(duration);
      consoleService.scrollToBottom();
    }
    return _cc;
  }
}

export { RouterService };
