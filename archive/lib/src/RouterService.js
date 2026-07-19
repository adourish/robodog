import OpenAI from "openai";

import { PerformanceCalculator } from "./PerformanceCalculator";
import { FormatService } from "./FormatService";
import { ConsoleService } from "./ConsoleService";
import { SearchService } from "./SearchService";
import { MCPService } from "./MCPService";
import { ProviderService } from "./ProviderService";
import { RouterModel } from "./RouterModel";
const formatService = new FormatService();
const consoleService = new ConsoleService();
const searchService = new SearchService();
const providerService = new ProviderService();
const mcpService = new MCPService();
class RouterService {
  constructor() {

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

  async getStreamCompletion(
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
    useDefault,
    bodySummary,

    setTotalChars
  ) {


    try {
      setThinking("🐱");
      const openai = this.getOpenAI(model, useDefault);
      const payload = { model, messages, temperature, top_p, frequency_penalty, presence_penalty, stream: true }
      const requestOpts = this.getRequestOptions(model, useDefault)
      setThinking("🦍");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(text, "user"),
      ]);
      consoleService.scrollToBottom();
      const stream = await openai.chat.completions.create(payload, requestOpts);
      let assistantText = "";
      for await (const chunk of stream) {
        const delta = chunk.choices?.[0]?.delta?.content;
        if (delta) {
          assistantText += delta;
        }

        setThinking("🐗");
        setContent([
          ...content,
          formatService.getMessageWithTimestamp(text, "user"),
          formatService.getMessageWithTimestamp(assistantText, "assistant"),
        ]);
        consoleService.scrollToBottom();
      }
      setThinking("🦓");
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
    useDefault,
    setTotalChars
  ) {
    // 1) show initial thinking state
    setThinking("🐴");
    // 2) detect /include
    const scan = userText + " " + knowledge;
    const idx = scan.search(/\/include\b/i);
    if (idx !== -1) {
      const includeCmd = scan.substring(idx).trim();
      const mainText = scan.substring(0, idx).trim();
      try {
        // parse the /include command
        const inc = mcpService.parseInclude(includeCmd);
        if (!inc) throw new Error("Bad include syntax");
        setThinking("🐳");
        // fetch included files
        let included = [];
        if (inc.type === "all") {
          const res = await mcpService.callMCP("GET_ALL_CONTENTS", {});
          included = res.contents;
        } else if (inc.type === "file") {
          const s = await mcpService.callMCP("SEARCH", {
            root: inc.file,
            pattern: inc.file,
            recursive: true
          });
          if (!s.matches.length) throw new Error(`No file ${inc.file}`);
          const f = await mcpService.callMCP("READ_FILE", { path: s.matches[0] });
          included.push({ path: f.path, content: f.content });
        } else {
          // pattern or dir
          const s = await mcpService.callMCP("SEARCH", {
            root: inc.dir || "",
            pattern: inc.pattern || "*",
            recursive: inc.recursive
          });
          if (!s.matches.length) throw new Error(`No matches for ${inc.pattern || inc.dir}`);
          for (let p of s.matches) {
            const f = await mcpService.callMCP("READ_FILE", { path: p });
            included.push({ path: f.path, content: f.content });
          }
        }

        // stitch them into a single “/include:” system message
        setThinking("🐕");
        let body = "/include:\n";
        let fileTokenTotal = 0;
        let bodySummary = `${includeCmd}:\n`;
        for (let i of included) {
          body += `--- file: ${i.path} ---\n${i.content}\n\n`;
          const c = consoleService.calculateTokens(i.content);
          fileTokenTotal += c;
          bodySummary += `Include: ${i.path} (${c} tokens)\n`;
        }

        // recalc total tokens if you need to display it
        const cContext = consoleService.calculateTokens(context);
        const cUser = consoleService.calculateTokens(userText);
        const cKnow = consoleService.calculateTokens(knowledge);
        const _totalChars = cContext + cUser + cKnow + fileTokenTotal;
        setTotalChars && setTotalChars(_totalChars);

        // show the user what we’re sending
        const prompt = userText + "\n" + bodySummary + "Include total tokens: " + _totalChars;
        setThinking("📤");
        setContent([
          ...content,
          formatService.getMessageWithTimestamp(prompt, "user")
        ]);
        consoleService.scrollToBottom();

        // inject the include as system roles into the existing messages
        const aug = [
          ...messages,
          { role: "system", content: body },
          {
            role: "system",
            content:
              "Do not repeat included files unless you have modified the content based on a prompt."
          }
        ];
        setThinking("🦫");

        // finally call the normal streaming completion with the augmented messages
        return this.getStreamCompletion(
          model,
          aug,
          temperature,
          top_p,
          frequency_penalty,
          presence_penalty,
          max_tokens,
          setThinking,
          setContent,
          setMessage,
          content,
          prompt,
          currentKey,
          context,
          knowledge,
          useDefault,
          bodySummary,
          setTotalChars
        );
      } catch (err) {
        // ANY error in include parsing or MCP calls → fallback
        console.warn("Include processing failed, proceeding WITHOUT include:", err);
        setMessage("⚠️ Unable to fetch included content, continuing without include.");
        // restore the normal user message
        setContent([
          ...content,
          formatService.getMessageWithTimestamp(userText, "user")
        ]);
        // and proceed with the original messages unmodified
        return this.getStreamCompletion(
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
          useDefault,
          null,
          setTotalChars
        );
      }
    }

    // 3) no /include found → normal path
    return this.getStreamCompletion(
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
      useDefault,
      null,
      setTotalChars
    );
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
      routerModel.size,
      routerModel.scrollToBottom,
      routerModel.setKnowledge,
      routerModel.setTotalChars
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
    scrollToBottom,
    setKnowledge,
    setTotalChars
  ) {
    // 1) Validate incoming `content`
    if (!Array.isArray(content)) {
      const errorMsg = "Invalid parameter: ‘content’ must be an array of messages.";
      setThinking("⚠️");
      const hist = [
        // preserve whatever was there if it was an array
        ...(Array.isArray(content) ? content : []),
        formatService.getMessageWithTimestamp(text, "user"),
        formatService.getMessageWithTimestamp(errorMsg, "error")
      ];
      setContent(hist);
      setMessage(errorMsg);
      scrollToBottom();
      return;
    }

    setThinking("💭");

    // 2) Load & validate config JSON
    let config;
    try {
      config = providerService.getJson();
    } catch (e) {
      const errorMsg = "Configuration error: unable to parse YAML. Please check your YAML syntax.";
      setThinking("⚠️");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(text, "user"),
        formatService.getMessageWithTimestamp(errorMsg, "error")
      ]);
      setMessage(errorMsg);
      scrollToBottom();
      return;
    }
    if (!config || !config.configs) {
      const errorMsg = "Configuration missing: no ‘configs’ block found. Please provide a valid config.";
      setThinking("⚠️");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(text, "user"),
        formatService.getMessageWithTimestamp(errorMsg, "error")
      ]);
      setMessage(errorMsg);
      scrollToBottom();
      return;
    }

    // 3) Lookup model
    const _model = providerService.getModel(model);
    if (!_model) {
      const available = (providerService.getModels() || [])
        .map(m => m.model)
        .join(", ") || "(none)";
      const errorMsg = `Model not found: ‘${model}’. Available models: ${available}.`;
      setThinking("⚠️");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(text, "user"),
        formatService.getMessageWithTimestamp(errorMsg, "error")
      ]);
      setMessage(errorMsg);
      scrollToBottom();
      return;
    }

    // 4) Lookup provider
    let _provider = null;
    if (_model.provider) {
      _provider = providerService.getProvider(_model.provider);
    }
    if (!_provider || !_provider.provider) {
      const errorMsg = `Provider not configured for model ‘${model}’. Expected provider name: ‘${_model.provider}’. Please update your provider settings.`;
      setThinking("⚠️");
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(text, "user"),
        formatService.getMessageWithTimestamp(errorMsg, "error")
      ]);
      setMessage(errorMsg);
      scrollToBottom();
      return;
    }

    // 5) Build the prompt messages
    const systemRole = ["o1", "o1-mini"].includes(model) ? "user" : "system";
    const messages = [
      { role: "user", content: "Chat History:" + context },
      { role: "user", content: "Knowledge Base:" + knowledge },
      { role: "user", content: "Question:" + text },
      {
        role: systemRole,
        content:
          "Instruction 1: Analyze the provided 'Chat History:' and 'Knowledge Base:' to understand and answer the user's 'Question:'. Do not provide answers based solely on the chat history or context."
      }
    ];

    // 6) Route to the correct handler
    let matched = false;
    let resultContent = content;

    try {
      if (model === "dall-e-3") {
        matched = true;
        resultContent = await this.handleDalliRestCompletion(
          model, messages,
          temperature, top_p, frequency_penalty, presence_penalty,
          max_tokens, setThinking, setContent, setMessage,
          content, text, currentKey, context, knowledge,
          size, true
        );
      } else if (model === "search") {
        matched = true;
        resultContent = await searchService.search(
          text, setThinking, setMessage, setContent, content
        );
      } else if (_model.provider === "openAI" && _model.stream) {
        matched = true;
        resultContent = await this.handleStreamCompletion(
          model, messages,
          temperature, top_p, frequency_penalty, presence_penalty,
          max_tokens, setThinking, setContent, setMessage,
          content, text, currentKey, context, knowledge,
          true, setTotalChars
        );
      } else if (_model.provider === "openRouter" && _model.stream) {
        matched = true;
        resultContent = await this.handleStreamCompletion(
          model, messages,
          temperature, top_p, frequency_penalty, presence_penalty,
          max_tokens, setThinking, setContent, setMessage,
          content, text, currentKey, context, knowledge,
          false, setTotalChars
        );
      } else if (_model.stream) {
        matched = true;
        resultContent = await this.handleStreamCompletion(
          model, messages,
          temperature, top_p, frequency_penalty, presence_penalty,
          max_tokens, setThinking, setContent, setMessage,
          content, text, currentKey, context, knowledge,
          true, setTotalChars
        );
      }

      if (!matched) {
        const errorMsg = `Unsupported combination: model='${model}', provider='${_model.provider}', stream='${_model.stream}'.`;
        setThinking("⚠️");
        setContent([
          ...content,
          formatService.getMessageWithTimestamp(text, "user"),
          formatService.getMessageWithTimestamp(errorMsg, "error")
        ]);
        setMessage(
          `${errorMsg} Please update your configuration or choose a supported model.`
        );
        scrollToBottom();
        return;
      }

      setThinking("🦥");
      return resultContent;
    } catch (err) {
      // 7) Catch-all unexpected errors
      setThinking("🐛");
      const errMsg = "Unexpected error: " + this.formatErrorMessage(err);
      setContent([
        ...content,
        formatService.getMessageWithTimestamp(text, "user"),
        formatService.getMessageWithTimestamp(errMsg, "error")
      ]);
      setMessage(errMsg);
      scrollToBottom();
      return;
    }
  }

}

export { RouterService };
