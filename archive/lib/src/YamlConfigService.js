


class YamlConfigService {
    constructor() {
      console.debug('ProviderService init')
    }
    getDefaults(){
      var yamlstring = `  
configs:
  providers:
    - provider: openAI
      baseUrl: "https://api.openai.com"
      apiKey: "<open ai token>"
      httpReferer: "https://adourish.github.io"
    - provider: openRouter
      baseUrl: "https://openrouter.ai/api/v1"
      apiKey: "<open router token>"
      httpReferer: "https://adourish.github.io"
    - provider: searchAPI
      baseUrl: "https://google-search74.p.rapidapi.com"
      apiKey: "<search token>"
      httpReferer: "https://adourish.github.io"
  
  mcpServer:
    baseUrl: "http://localhost:2500"  
    apiKey:   "testtoken"  

  specialists:
    - specialist: nlp
      resume: natural language processing, chatbots, content generation, language translation
    - specialist: gi
      resume: generates images from textual descriptions. understanding and interpreting textual descriptions 
    - specialist: search
      resume: generate simple search results

  models:
    - provider: openRouter
      model: openai/gpt-5-mini
      stream: true
      specialist: nlp
      about: "Best for performance. Context window: 1.05M tokens. Competitive in Academia (#2), Marketing/Seo (#3), Health (#4), Legal (#4), Science (#4)."
    - provider: openRouter
      model: GPT-4o-mini
      stream: true
      specialist: nlp
      about: "Best for most questions. Context window: 1.05M tokens. Pricing: $0.40/M input, $1.60/M output."
    - provider: openAI
      model: o4-mini
      stream: true
      specialist: nlp
      about: "Biggest model with 200k context window and world view. Best for critical thinking. Context window: 200K tokens."
    - provider: openAI
      model: o1
      stream: true
      specialist: nlp
      about: "Big model with 128k context window and small world view. Good for critical thinking. Context window: 128K tokens."
    - provider: openRouter
      model: openai/o4-mini
      stream: true
      specialist: nlp
      about: "Best for big content. Context window: 200K tokens."
    - provider: openRouter
      model: deepseek/deepseek-r1
      stream: true
      specialist: nlp
      about: "Best for summarizing. Context window: 128K tokens. Model size: 671B parameters (37B active). Performance: #2 in Roleplay, #6 in Translation, #9 in Programming, #10 in Science. Supports thinking and non-thinking modes."
    - provider: openRouter
      model: google/gemini-2.5-pro
      stream: true
      specialist: nlp
      about: "Best for speed. Context window: 1.05M tokens. Performance: #3 in Health, #5 in Marketing, Roleplay, Academia, Science. Advanced reasoning, coding, mathematics, scientific tasks. Pricing: $1.25/M input, $10/M output."
    - provider: openRouter
      model: qwen/qwen3-coder
      stream: true
      specialist: nlp
      about: "Best for large docs when speed is not an issue. Context window: 262K tokens. Model size: 480B parameters (35B active). Optimized for agentic coding tasks. Performance: #3 in Programming, #7 in Technology, #8 in Science. Pricing: $0.20/M input, $0.80/M output."
    - provider: openRouter
      model: anthropic/claude-sonnet-4
      stream: false
      specialist: gi
      about: "Best for creating images."
    - provider: openRouter
      model: x-ai/grok-code-fast-1
      stream: false
      specialist: search
      about: "Best for searching. Context window: 256K tokens. Performance: #1 in Programming, #3 in Technology, #6 in Marketing/Seo, #10 in Trivia. Speedy and economical reasoning model. Pricing: $0.20/M input, $1.50/M output."
    - provider: searchAPI
      model: search
      stream: false
      specialist: search
      about: "Best for searching. Context window: 256K tokens. Performance: #1 in Programming, #3 in Technology, #6 in Marketing/Seo, #10 in Trivia. Speedy and economical reasoning model. Pricing: $0.20/M input, $1.50/M output."
      
      `
      return yamlstring;
    }
  }

  export { YamlConfigService }