# robotdog 

# About

Robot Dog is a UI to call openai GPT models and is built using React, TypeScript, and Webpack. 

# Features

* No need to install npm or run a node server
  * The webpack build creates two files
  * It compiles into a single HTML file named `robodog.html` and a single JavaScript bundle `robotdog.bundle.js`.
  * You do not need to install npm to run the tool.
  * A prompt will ask you for your API key. it is stored in local storage.
* All chat history is added to the ‘chat context’ text box. 
  * If you have ever had an argument with the GPT AI, you know why this is here. You can add and remove chat context at any time.
* Add your knowledge. Any code or documents you need to ask the AI about can go here.
* Add your question.
* Switch between GPT3.5 and GPT4 models without losing chat context. 
  * Validate your questions and answers on a different model. 
  * In the future, you may be able to validate using a different LLM provider.
  * Switch between cheap and expensive models.

![Robot Dog Screenshot](screenshot.png)

# Build

* npm install
* npm install openai
* npm run build

# Run

* Open in a `.\dist\robodog.html` in a browser.

# Commands

* /GPT3 - switch to GPT 3.5 turbo model.
* /GPT4 - switch to latest GPT 4 model.
* /help - get help
* /reset - Reset your API key

