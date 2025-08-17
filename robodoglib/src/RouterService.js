import OpenAI from "openai";

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

async callMCPbak(op, payload, timeoutMs = 5000) {
    let netLib = null;
    try {
      // only works in Node.js—will throw in a browser bundle
      // (or you can test typeof process !== 'undefined' && process.versions.node)
      netLib = require("net");
    } catch (e) {
      // net not available, immediately bail
    }

    if (!netLib || typeof netLib.Socket !== "function") {
      // no net.Socket → force fallback in handleStreamCompletion
      return Promise.reject(new Error("TCP unsupported or 'net' not found"));
    }

    const cmd = `${op} ${JSON.stringify(payload)}\n`;
    return new Promise((resolve, reject) => {
      const client = new netLib.Socket();
      let buffer = "";

      client.setTimeout(timeoutMs, () => {
        client.destroy();
        reject(new Error("MCP call timed out"));
      });

      client.connect(2500, "127.0.0.1", () => {
        client.write(cmd);
      });

      client.on("data", (data) => {
        buffer += data.toString("utf8");
      });

      client.on("end", () => {
        const lines = buffer.trim().split("\n");
        const last = lines[lines.length - 1];
        try {
          const json = JSON.parse(last);
          resolve(json);
        } catch (e) {
          reject(new Error("Failed to parse MCP JSON: " + e.message));
        }
      });

      client.on("error", (err) => {
        reject(err);
      });
    });
  }
  async callMCP(op, payload, timeoutMs = 5000) {
    const cmd = `${op} ${JSON.stringify(payload)}\n`;

    // if we detect a browser, use fetch
    if (typeof window !== 'undefined' && typeof fetch === 'function') {
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), timeoutMs);
      let text;
      try {
        const res = await fetch(RouterService.MCP_SERVER_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain' },
          body: cmd,
          signal: controller.signal
        });
        clearTimeout(id);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        text = await res.text();
      } catch (err) {
        clearTimeout(id);
        throw err;
      }
      // MCP always ends its JSON response on the last line
      const lines = text.trim().split('\n');
      try {
        return JSON.parse(lines[lines.length - 1]);
      } catch (e) {
        throw new Error("Failed to parse MCP JSON: " + e.message);
      }
    }

    // otherwise, fall back to Node TCP socket
    let netLib;
    try { netLib = require("net"); } catch (_) { throw new Error("TCP/net unsupported"); }
    return new Promise((resolve, reject) => {
      const client = new netLib.Socket();
      let buffer = "";
      client.setTimeout(timeoutMs, () => {
        client.destroy();
        reject(new Error("MCP call timed out"));
      });
      client.connect(2500, "127.0.0.1", () => client.write(cmd));
      client.on("data", d => buffer += d.toString("utf8"));
      client.on("end", () => {
        const lines = buffer.trim().split("\n");
        try { resolve(JSON.parse(lines[lines.length - 1])); }
        catch (e) { reject(new Error("Failed to parse MCP JSON: " + e.message)); }
      });
      client.on("error", reject);
    });
  }

  summarizeMcpResult(obj) {
    try {
      return Object.entries(obj)
        .map(([k, v]) => {
          if (Array.isArray(v)) return `${k}=[${v.length}]`;
          if (typeof v === "string")
            return `${k}="${v.slice(0, 30)}…"(${v.length})`;
          if (typeof v === "object") return `${k}={…}`;
          return `${k}=${v}`;
        })
        .join(", ");
    } catch {
      return JSON.stringify(obj).slice(0, 100) + "…";
    }
  }

  async handleStreamCompletion(
    model, messages, temperature, top_p,
    frequency_penalty, presence_penalty, max_tokens,
    setThinking, setContent, setMessage,
    content, userText, currentKey, context, knowledge, useDefault
  ) {
    const fileOpRegex = /\b(list files|read file|update file|create file|delete file)\b/i;

    // 1) No file‐op → fall back to normal streaming
    if (!fileOpRegex.test(userText)) {
      return this.handleStreamCompletionBak2(
        model, messages, temperature, top_p,
        frequency_penalty, presence_penalty, max_tokens,
        setThinking, setContent, setMessage,
        content, userText, currentKey, context, knowledge, useDefault
      );
    }

    // 2) Ask LLM to emit exactly one JSON {op,args}
    const systemPrompt = {
      role: 'system',
      content:
        'If the user wants you to list/read/update/create/delete files, ' +
        'output exactly one JSON object with fields "op" and "args", and nothing else. ' +
        'E.g. { "op": "LIST_FILES", "args": {} } Otherwise, answer normally.'
    };
    const userPrompt = { role: 'user', content: userText };

    let jsonReply;
    try {
      const resp = await this.getOpenAI(model, useDefault)
        .chat.completions.create({
          model,
          messages: [systemPrompt, userPrompt],
          temperature, top_p, frequency_penalty, presence_penalty,
          max_tokens: max_tokens > 0 ? max_tokens : undefined,
          stream: false
        });
      jsonReply = resp.choices[0]?.message?.content.trim() || "";
    } catch (err) {
      console.warn("[RouterService] JSON‐command LLM failed, fallback:", err);
      return this.handleStreamCompletionBak2(
        model, messages, temperature, top_p,
        frequency_penalty, presence_penalty, max_tokens,
        setThinking, setContent, setMessage,
        content, userText, currentKey, context, knowledge, useDefault
      );
    }

    // 3) Parse out JSON
    let cmd;
    try {
      const m = jsonReply.match(/\{[\s\S]*\}/);
      if (!m) throw new Error("no JSON");
      cmd = JSON.parse(m[0]);
      if (typeof cmd.op !== 'string' || typeof cmd.args !== 'object')
        throw new Error("bad shape");
    } catch (err) {
      console.warn("[RouterService] parse JSON cmd failed, fallback:", err, "raw:", jsonReply);
      return this.handleStreamCompletionBak2(
        model, messages, temperature, top_p,
        frequency_penalty, presence_penalty, max_tokens,
        setThinking, setContent, setMessage,
        content, userText, currentKey, context, knowledge, useDefault
      );
    }

    // 4) Invoke MCP over raw TCP
    let mcpResult;
    try {
      mcpResult = await this.callMCP(cmd.op, cmd.args);
    } catch (err) {
      console.warn(
        `[RouterService] MCP TCP call failed, fallback to chat stream:`,
        err
      );
      return this.handleStreamCompletionBak2(
        model, messages, temperature, top_p,
        frequency_penalty, presence_penalty, max_tokens,
        setThinking, setContent, setMessage,
        content, userText, currentKey, context, knowledge, useDefault
      );
    }

    // 5) Log a one-line summary of exactly what came back
    const summary = this.summarizeMcpResult(mcpResult);
    console.info(
      `[RouterService] MCP ${cmd.op} args=${JSON.stringify(cmd.args)} → ${summary}`
    );

    // 6) stitch JSON command + result into the UI history
    const history = [
      ...content,
      FormatService.getMessageWithTimestamp(JSON.stringify({op: cmd.op, args: cmd.args}), "assistant"),
      FormatService.getMessageWithTimestamp(JSON.stringify(mcpResult), "assistant"),
    ];
    setContent(history);
    setThinking("🦥");
    consoleService.stash(currentKey, context, knowledge, userText, history);

    return history;
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
