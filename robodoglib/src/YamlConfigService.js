


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
      apiKey: "key"
	  http-Referer: "https://adourish.github.io"
    - provider: openRouter
      baseUrl: "https://openrouter.ai/api/v1"
      apiKey: "key"
	  http-Referer: "https://adourish.github.io"
    - provider: searchAPI
      baseUrl: "https://google-search74.p.rapidapi.com"
      apiKey: "key"
	  http-Referer: "https://adourish.github.io"
      
  specialists:
    - specialist: nlp
      resume: natural language processing, chatbots, content generation, language translation
    - specialist: gi
      resume: generates images from textual descriptions. understanding and interpreting textual descriptions 
    - specialist: search
      resume: generate simple search results

  models:
    - provider: openAI
      model: gpt-4
      stream: true
      specialist: nlp
      about: best for performance 
    - provider: openRouter
      model: GPT-4o-mini
      stream: true
      specialist: nlp
      about: best for most questions
    - provider: openAI
      model: o4-mini
      stream: true
      specialist: nlp
      about: biggest model with 200k context window and world view. Best for critical thinking.
    - provider: openAI
      model: o1
      stream: true
      specialist: nlp
      about: big model with 128k context window and small world view. Good for critical thinking.
    - provider: llamaAI
      model: llama3-70b
      stream: false
      specialist: nlp
      about: best for big content
    - provider: openAI
      model: gpt-4o
      stream: true
      specialist: nlp
      about: best for summerizing
    - provider: openAI
      model: gpt-4-turbo
      stream: true
      specialist: nlp
      about: best for speed
    - provider: openAI
      model: gpt-3.5-turbo-16k
      stream: true
      specialist: nlp
      about: best for large docs when speed is not an issue
    - provider: openAI
      model: dall-e-3
      stream: false
      specialist: gi
      about: best for creating images
    - provider: searchAPI
      model: search
      stream: false
      specialist: search
      about: best for searching
      
      `
      return yamlstring;
    }
  }

  export { YamlConfigService }