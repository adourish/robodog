


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
  
    models:
      - provider: openAI
        model: gpt-4
        stream: true
        modelType: text-to-text
      - provider: openAI
        model: gpt-3.5-turbo
        stream: true
        modelType: text-to-text
      - provider: lamaAI
        model: llama3-70b
        stream: false
        modelType: text-to-text
      - provider: openAI
        model: gpt-4o
        stream: true
        modelType: text-to-text
      - provider: openAI
        model: gpt-4-turbo
        stream: true
        modelType: text-to-text
      - provider: openAI
        model: gpt-4-turbo
        stream: true
        modelType: text-to-text
      - provider: openAI
        model: gpt-3.5-turbo
        stream: openai
        modelType: text-to-text
      - provider: openAI
        model: gpt-3.5-turbo-16k
        stream: true
        modelType: text-to-text
      - provider: openAI
        model: dall-e-3
        stream: false
        modelType: text-to-image
      
      `
      return yamlstring;
    }
  }

  export { YamlConfigService }