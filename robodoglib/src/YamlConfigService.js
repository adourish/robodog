


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
        stream: true
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
        model: gpt-4-0613
        stream: true
        modelType: text-to-text
      - provider: openAI
        model: gpt-4o-mini
        stream: true
        modelType: text-to-text
      - provider: openAI
        model: dall-e-3
        stream: system
        modelType: text-to-image
      - provider: openAI
        model: gpt-4o-2024-05-13
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: gpt-4-turbo-2024-04-09
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: gpt-4-1106-preview
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: dall-e-2
        stream: system
        modelType: text-to-image
      - provider: openAI
        model: gpt-4o
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: gpt-4-turbo
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: tts-1-hd-1106
        stream: system
        modelType: text-to-speech
      - provider: openAI
        model: tts-1-hd
        stream: system
        modelType: text-to-speech
      - provider: openAI
        model: gpt-4-0125-preview
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: babbage-002
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: gpt-4-turbo-preview
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: text-embedding-3-small
        stream: system
        modelType: text-embedding
      - provider: openAI
        model: text-embedding-3-large
        stream: system
        modelType: text-embedding
      - provider: openAI
        model: gpt-3.5-turbo-0613
        stream: openai
        modelType: text-to-text
      - provider: openAI
        model: gpt-3.5-turbo-0301
        stream: openai
        modelType: text-to-text
      - provider: openAI
        model: gpt-3.5-turbo
        stream: openai
        modelType: text-to-text
      - provider: openAI
        model: gpt-3.5-turbo-instruct
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: gpt-3.5-turbo-instruct-0914
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: whisper-1
        stream: openai-internal
        modelType: text-to-text
      - provider: openAI
        model: text-embedding-ada-002
        stream: openai-internal
        modelType: text-embedding
      - provider: openAI
        model: gpt-3.5-turbo-16k
        stream: openai-internal
        modelType: text-to-text
      - provider: openAI
        model: davinci-002
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: gpt-3.5-turbo-16k-0613
        stream: openai
        modelType: text-to-text
      - provider: openAI
        model: tts-1-1106
        stream: system
        modelType: text-to-speech
      - provider: openAI
        model: gpt-3.5-turbo-0125
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: tts-1
        stream: openai-internal
        modelType: text-to-speech
      - provider: openAI
        model: gpt-3.5-turbo-1106
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: gpt-4o-mini-2024-07-18
        stream: system
        modelType: text-to-text
      - provider: openAI
        model: gpt-4o-mini
        stream: system
        modelType: text-to-text
      
      `
      return yamlstring;
    }
  }

  export { YamlConfigService }