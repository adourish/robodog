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

  isAndroid() {
    try {
      const userAgent = navigator.userAgent || navigator.vendor || window.opera;
      return /Android/i.test(userAgent);
    } catch (error) {
      console.error("Error determining if the device is Android:", error);
      return false; // Default value in case of an error
    }
  }

  getOpenAI(model, useDefault) {
    const _model = providerService.getModel(model);
    const _provider = providerService.getProvider(_model.provider);
    const _apiKey = _provider.apiKey;
    const _baseUrl = _provider.baseUrl; // e.g. “https://adourish.github.io”

    let _httpReferer = _provider.httpReferer;

    const isAndroidApp = this.isAndroid();

    if (isAndroidApp || useDefault) {
      // Do not include Referer for Android app calls
      console.log("Calling from Android app, skipping Referer header.");
      _httpReferer = null; // This will prevent setting it in the clientConfig
    } else if (!_httpReferer || _httpReferer.trim() === "") {
      _httpReferer = this.getRefererUrl(); // Use the referer from getRefererUrl if _httpReferer is empty or null
    }

    console.log(_model, _provider);

    let clientConfig = {
      apiKey: _apiKey,
      baseURL: _baseUrl,
      dangerouslyAllowBrowser: true,
      extraHeaders: {},
      headers: {},
    };
    if (useDefault) {
      clientConfig = {
        apiKey: _apiKey,
        dangerouslyAllowBrowser: true,
        extraHeaders: {},
        headers: {},
      };
    }
    // Only add the HTTP-Referer header if it's not null
    if (_httpReferer) {
      clientConfig.extraHeaders["HTTP-Referer"] = _httpReferer;
      clientConfig.headers["HTTP-Referer"] = _httpReferer;

    }

    const openai = new OpenAI(clientConfig);
    console.log(openai);
    return openai;
  }

  getRequestOptions(model, useDefault) {
    // grab the provider entry for this model
    const _model = providerService.getModel(model)
    const _provider = providerService.getProvider(_model.provider)
    let referer = _provider.httpReferer

    if (this.isAndroid() || useDefault) {
      referer = null
    }

    else if (!referer || referer.trim() === "") {
      referer = this.getRefererUrl()
    }

    // build the outgoing headers object
    const headers = {}
    if (referer) {
      headers["HTTP-Referer"] = referer
    }

    return { headers }
  }

  getRefererUrl() {

    return document.referrer || "https://adourish.github.io"; // Use a default if none
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
    knowledge,
    useDefault
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
    const openai = this.getOpenAI(model, useDefault);
    try {
      const response = await openai.chat.completions.create(_p2);
      if (response) {
        var _content = response.choices[0]?.message?.content;
        var _finish_reason = response.choices[0]?.finish_reason;
        _r.content = _content || "No content available";
        _r.finish_reason = _finish_reason || "No finish reason";
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
      const errorMessage = this.formatErrorMessage(error);
      console.error(errorMessage);
      setMessage("Error");
      _c = [
        ...content,
        formatService.getMessageWithTimestamp(errorMessage, "error"),
      ];
      setContent(_c);
    }
    return null;
  }

  static MCP_SERVER_URL = "http://localhost:2500";

  // 1) JSON‐schema for each MCP op
  static MCP_FUNCTIONS = [
    {
      name: "LIST_FILES",
      description: "List all files under the configured root folders",
      parameters: {
        type: "object",
        properties: {},
        required: []
      }
    },
    {
      name: "READ_FILE",
      description: "Read the contents of a file",
      parameters: {
        type: "object",
        properties: {
          path: {
            type: "string",
            description: "Absolute path to the file"
          }
        },
        required: ["path"]
      }
    },
    {
      name: "UPDATE_FILE",
      description: "Overwrite a file with new content",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Absolute path to the file" },
          content: { type: "string", description: "New file contents" }
        },
        required: ["path", "content"]
      }
    },
    // … add other ops (CREATE_FILE, DELETE_FILE, etc.) as needed
  ];

  async callMCP(op, payload) {
    const command = `${op} ${JSON.stringify(payload)}\n`;
    try {
      const res = await axios.post(
        RouterService.MCP_SERVER_URL,
        command,
        {
          headers: { "Content-Type": "text/plain" },
          responseType: "text"
        }
      );
      const lines = res.data.trim().split("\n");
      return JSON.parse(lines[lines.length - 1]);
    } catch (err) {
      console.error(`MCP call ${op} failed:`, err);
      throw err;
    }
  }

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
    userText,
    currentKey,
    context,
    knowledge,
    useDefault
  ) {
    // prepare our “functions” call:
    const openai = this.getOpenAI(model, useDefault);
    const requestOpts = this.getRequestOptions(model, useDefault);

    const firstPayload = {
      model,
      messages: [
        ...messages,
        { role: "user", content: userText }
      ],
      temperature,
      top_p,
      frequency_penalty,
      presence_penalty,
      max_tokens: max_tokens > 0 ? max_tokens : undefined,
      stream: true,
      functions: RouterService.MCP_FUNCTIONS,
      function_call: "auto"
    };

    // accumulate the function_call
    let funcName = "";
    let funcArgs = "";

    // 1st pass: let the model choose and emit a function_call
    try {
      const stream1 = await openai.chat.completions.create(
        firstPayload,
        requestOpts
      );

      for await (const chunk of stream1) {
        const delta = chunk.choices?.[0]?.delta;
        // collect the function_call name & arguments
        if (delta?.function_call) {
          if (delta.function_call.name) {
            funcName += delta.function_call.name;
          }
          if (delta.function_call.arguments) {
            funcArgs += delta.function_call.arguments;
          }
        }
      }
    } catch (err) {
      console.error("Error during function_call phase:", err);
      setMessage("Error");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(
          `Function‐calling failed: ${err.message}`,
          "error"
        )
      ]);
      return content;
    }

    // If the model did not pick any function, bail out
    if (!funcName) {
      setMessage("No function_call detected");
      return content;
    }

    // parse arguments and invoke MCP
    let mcpResult;
    try {
      const argsObj = JSON.parse(funcArgs);
      mcpResult = await this.callMCP(funcName, argsObj);
      console.debug(`MCP ${funcName} →`, mcpResult);
    } catch (err) {
      console.warn(`MCP ${funcName} invocation failed:`, err);
      mcpResult = { error: err.message };
    }

    // append the function_call and its result into the history
    const newMessages = [
      ...messages,
      { role: "user", content: userText },
      {
        role: "assistant",
        content: null,
        function_call: { name: funcName, arguments: funcArgs }
      },
      {
        role: "function",
        name: funcName,
        content: JSON.stringify(mcpResult)
      }
    ];

    // 2nd pass: ask the model to finish the answer based on the function result
    let finalText = "";
    try {
      const stream2 = await openai.chat.completions.create(
        {
          model,
          messages: newMessages,
          temperature,
          top_p,
          frequency_penalty,
          presence_penalty,
          stream: true,
          max_tokens: max_tokens > 0 ? max_tokens : undefined
        },
        requestOpts
      );

      for await (const chunk of stream2) {
        const delta = chunk.choices?.[0]?.delta?.content;
        if (delta) finalText += delta;

        setThinking("🤖");
        setContent([
          ...content,
          formatService.getMessageWithTimestamp(userText, "user"),
          formatService.getMessageWithTimestamp(finalText, "assistant")
        ]);
        consoleService.scrollToBottom();
      }

      // stash and return the final history
      const history = [
        ...content,
        formatService.getMessageWithTimestamp(userText, "user"),
        formatService.getMessageWithTimestamp(finalText, "assistant")
      ];
      setContent(history);
      setThinking("🦥");
      consoleService.stash(
        currentKey,
        context,
        knowledge,
        userText,
        history
      );
      return history;
    } catch (err) {
      console.error("Error during final assistant turn:", err);
      setMessage("Error");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(err.message, "error")
      ]);
      return content;
    }
  }

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
    userText,
    currentKey,
    context,
    knowledge,
    useDefault
  ) {
    // 1) detect if user is asking for file operations
    //    adjust this regex to taste (add UPDATE, DELETE, etc.)
    const fileOpRegex = /\b(read file|list files|update file|create file|delete file)\b/i;
    if (!fileOpRegex.test(userText)) {
      // no file‐op requested → fallback to normal chat streaming
      return await this.handleStreamCompletionBak2(
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
        userText,
        currentKey,
        context,
        knowledge,
        useDefault
      );
    }

    // 2) file-ops path: use OpenAI function-calling + MCP
    const openai = this.getOpenAI(model, useDefault);
    const requestOpts = this.getRequestOptions(model, useDefault);
    const firstPayload = {
      model,
      messages: [
        ...messages,
        { role: "user", content: userText }
      ],
      temperature,
      top_p,
      frequency_penalty,
      presence_penalty,
      max_tokens: max_tokens > 0 ? max_tokens : undefined,
      stream: true,
      functions: RouterService.MCP_FUNCTIONS,
      function_call: "auto"
    };

    // accumulate function_call
    let funcName = "";
    let funcArgs = "";

    // 2a) first pass: let the model pick a function
    try {
      const stream1 = await openai.chat.completions.create(
        firstPayload,
        requestOpts
      );
      for await (const chunk of stream1) {
        const delta = chunk.choices?.[0]?.delta;
        if (delta?.function_call) {
          if (delta.function_call.name) {
            funcName += delta.function_call.name;
          }
          if (delta.function_call.arguments) {
            funcArgs += delta.function_call.arguments;
          }
        }
      }
    } catch (err) {
      console.error("Error during function_call phase:", err);
      setMessage("Error");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(
          `Function‐calling failed: ${err.message}`,
          "error"
        )
      ]);
      return content;
    }

    if (!funcName) {
      setMessage("No function_call detected");
      return content;
    }

    // 2b) invoke MCP
    let mcpResult;
    try {
      const argsObj = JSON.parse(funcArgs);
      mcpResult = await this.callMCP(funcName, argsObj);
      console.debug(`MCP ${funcName} →`, mcpResult);
    } catch (err) {
      console.warn(`MCP ${funcName} invocation failed:`, err);
      mcpResult = { error: err.message };
    }

    // 2c) stitch back into messages
    const newMessages = [
      ...messages,
      { role: "user", content: userText },
      {
        role: "assistant",
        content: null,
        function_call: { name: funcName, arguments: funcArgs }
      },
      {
        role: "function",
        name: funcName,
        content: JSON.stringify(mcpResult)
      }
    ];

    // 2d) second pass: let the model finish the answer
    let finalText = "";
    try {
      const stream2 = await openai.chat.completions.create(
        {
          model,
          messages: newMessages,
          temperature,
          top_p,
          frequency_penalty,
          presence_penalty,
          stream: true,
          max_tokens: max_tokens > 0 ? max_tokens : undefined
        },
        requestOpts
      );

      for await (const chunk of stream2) {
        const delta = chunk.choices?.[0]?.delta?.content;
        if (delta) finalText += delta;

        setThinking("🤖");
        setContent([
          ...content,
          formatService.getMessageWithTimestamp(userText, "user"),
          formatService.getMessageWithTimestamp(finalText, "assistant")
        ]);
        consoleService.scrollToBottom();
      }

      const history = [
        ...content,
        formatService.getMessageWithTimestamp(userText, "user"),
        formatService.getMessageWithTimestamp(finalText, "assistant")
      ];
      setContent(history);
      setThinking("🦥");
      consoleService.stash(currentKey, context, knowledge, userText, history);
      return history;
    } catch (err) {
      console.error("Error during final assistant turn:", err);
      setMessage("Error");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(err.message, "error")
      ]);
      return content;
    }
  }

  async handleStreamCompletionBak2(
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
    useDefault
  ) {


    try {
      const openai = this.getOpenAI(model, useDefault);
      const payload = { model, messages, temperature, top_p, frequency_penalty, presence_penalty, stream: true }
      const requestOpts = this.getRequestOptions(model, useDefault)

      const stream = await openai.chat.completions.create(payload, requestOpts);
      let assistantText = "";
      for await (const chunk of stream) {
        const delta = chunk.choices?.[0]?.delta?.content;
        if (delta) {
          assistantText += delta;
        }

        setThinking("🤖");
        setContent([
          ...content,
          formatService.getMessageWithTimestamp(text, "user"),
          formatService.getMessageWithTimestamp(assistantText, "assistant"),
        ]);
        consoleService.scrollToBottom();
      }

      // Finalize
      const finalContent = assistantText;
      const newHistory = [
        ...content,
        formatService.getMessageWithTimestamp(text, "user"),
        formatService.getMessageWithTimestamp(finalContent, "assistant"),
      ];

      setContent(newHistory);
      consoleService.stash(currentKey, context, knowledge, text, newHistory);

      return newHistory;
    }
    catch (err) {
      const msg = this.formatErrorMessage(err);
      console.error(msg);
      setMessage("Error");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(msg, "error"),
      ]);
      return content;
    }
  }

  // handle open ai stream completions
  async bakhandleStreamCompletion(
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
    useDefault
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
      const openai = this.getOpenAI(model, useDefault);
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

        var _cc = [
          ...content,
          formatService.getMessageWithTimestamp(text, "user"),
          formatService.getMessageWithTimestamp(_content, "assistant"),
        ];
        setContent(_cc);

        consoleService.stash(currentKey, context, knowledge, text, _cc);
      }
      return _cc || content; // ensure a return value is always returned
    } catch (error) {
      const errorMessage = this.formatErrorMessage(error);
      console.error(errorMessage);
      setMessage("Error");
      _c = [
        ...content,
        formatService.getMessageWithTimestamp(errorMessage, "error"),
      ];
      setContent(_c);

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
    size,
    useDefault
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
      const openai = this.getOpenAI(model, useDefault);
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
    } catch (error) {
      const errorMessage = this.formatErrorMessage(error);
      console.error(errorMessage);
      setMessage("Error");
      _c = [
        ...content,
        formatService.getMessageWithTimestamp(errorMessage, "error"),
      ];
      setContent(_c);
    }
    return _c;
  }

  formatErrorMessage(error) {
    let message = `Error occurred: ${error.message || "Unknown error"}`;

    // Add information from deep objects
    if (error.response) {
      message += `, Response: ${JSON.stringify(
        error.response.data || "No data"
      )}`;
    }
    if (error.stack) {
      message += `, Stack: ${error.stack}`;
    }
    if (error.metadata) {
      message += `, Metadata: ${JSON.stringify(error.metadata || "No data")}`;
    }
    if (error.error) {
      message += this.formatErrorMessage(error.error);
    }
    if (error.code) {
      message += `, Code: ${JSON.stringify(error.code || "No data")}`;
    }
    if (error.message) {
      message += `, Message: ${JSON.stringify(error.message || "No data")}`;
    }
    return message;
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
      },
    ];

    setThinking(formatService.getRandomEmoji());
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
            size,
            true
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
            knowledge,
            true
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
            knowledge,
            false
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
            knowledge,
            true
          );
        } else if (_model.stream === true) {
          console.log("rounter openAI handleRestCompletion");
          console.log(
            "rounter fall through " +
            _model.provider +
            " handleStreamCompletion"
          );
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
            knowledge,
            true
          );
        } else {
          console.log("no matching model condigtions");
        }
      } else {
        console.log("no matching provider or model");
      }
      setThinking("🦥");
    } catch (error) {
      setThinking("🐛");
      const errorMessage = this.formatErrorMessage(error);
      console.error(errorMessage);
      setMessage("Error");
    } finally {
      consoleService.scrollToBottom();
    }
    return _cc;
  }
}

export { RouterService };
