# Robodog AI

# About

Robodog AI assistant is a lightweight and portable UI that utilizes OpenAI GPT models and is built with React, TypeScript, and Webpack. It does not require a backend server, as it primarily relies on OpenAI for its functionality.

# Features

Robodog AI Assistant provides a flexible runtime, allowing installation on a laptop, Github pages, or a personal static file server without the need to install npm or run a node server. The webpack build effortlessly generates two files, compiling into a single HTML file named `robodog.html` and a JavaScript bundle called `robotdog.bundle.js`. Additionally, the tool does not require npm installation as it simply prompts for the API key, which is stored in local storage.

All chat history is conveniently accumulated in the 'chat context' text box, ensuring seamless continuation of conversations with the GPT AI. The feature allows users to add or remove chat contexts as needed. Users can also incorporate their knowledge, code, or documents for AI assistance and pose questions for optimized interactions.

Furthermore, users can effortlessly switch between GPT3.5 and GPT4 models without losing their chat context, enabling them to validate their questions and answers on a different model. Additionally, the system allows flexibility in choosing between cost-effective and higher-priced models, ensuring diverse options for tailored AI interactions.

# Indicators

* [3432/9000] - estimated remaining context
* [rest] - rest completion mode
* [stream] - stream completion mode
* [🦥] - ready
* [🦧] - thinking
* [gpt-3.5-turbo-1106] - GPT model
* [🐘] - Context + knowledge + chat is dangerously large.
* [🐁] - Context + knowledge + chat is acceptable.


# Screenshots

![Screenshot](screenshot.png)

![Features](screenshot2.png)

# Build

* cd robodog
* npm install
* npm install openai
* npm install zip-webpack-plugin
* npm run build

# Run

* Open in a `.\dist\robodog.html` in a browser.

# Commands

* /gpt-3.5-turbo - switch to gpt-3.5-turbo-1106 model (4,096 tokens).
* /gpt-3.5-turbo-16k - switch to gpt-3.5-turbo-16k model (16,385 tokens).
* /gpt-3.5-turbo-1106 - switch to gpt-3.5-turbo-1106 model (16,385 tokens).
* /gpt-4 - switch to gpt-4 model (8,192 tokens).
* /gpt-4-1106-preview - switch to gpt-4-1106-preview model (128,000 tokens).
* /help - get help.
* /clear - get help.
* /rest - use rest completions
* /stream - use stream completions
* /reset - Reset your API key

# Try

* [Robodog](https://adourish.github.io/robodog/robodog/dist/)

# Download

* [Download Robodog](https://github.com/adourish/robodog/tree/main/robodog/dist/robodog.zip)
