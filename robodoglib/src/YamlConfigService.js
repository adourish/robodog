


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
      apiKey: ""
    - provider: lamaAI
      baseUrl: "https://api.llama-api.com"
      apiKey: ""
    - provider: searchAPI
      baseUrl: "https://google-search74.p.rapidapi.com"
      apiKey: ""
      
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
    - provider: openAI
      model: gpt-3.5-turbo
      stream: true
      specialist: nlp
    - provider: lamaAI
      model: llama3-70b
      stream: false
      specialist: nlp
    - provider: openAI
      model: gpt-4o
      stream: true
      specialist: nlp
    - provider: openAI
      model: gpt-4-turbo
      stream: true
      specialist: nlp
    - provider: openAI
      model: gpt-3.5-turbo
      stream: true
      specialist: nlp
    - provider: openAI
      model: gpt-3.5-turbo-16k
      stream: true
      specialist: nlp
    - provider: openAI
      model: dall-e-3
      stream: false
      specialist: gi
    - provider: searchAPI
      model: search
      stream: false
      specialist: search
      
      `
      return yamlstring;
    }
  }

  export { YamlConfigService }