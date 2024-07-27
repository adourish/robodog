# Robodog AI

# About

Robodog is a GPT client with support for gpt-3.5-turbo, gpt-4, gpt-4-turbo, dall-e-3, and gpt-3.5-turbo-16k. A highly portal GPT UI with support for upload files, save points, and temperature configurations. 

# Try robodog

- [Robodog web](https://adourish.github.io/robodog/robodog/dist/)
- [Robodog Android](https://play.google.com/store/apps/details?id=com.unclebulgaria.robodog)
- [npm install robodoglib](https://www.npmjs.com/package/robodoglib)
- [npm install robodogcli](https://www.npmjs.com/package/robodogcli)
- [npm install robodog](https://www.npmjs.com/package/robodog)

# Configure providers and models
- Click ⚙️ to configure

![Screenshot](screenshot-quick.png)

# History

## Version 1.0.0
- Support for /models <model>. Most text based models are supported
- Support for /gpt-3.5-turbo and /gpt-4 quick
- Support for rest completions

## Version 1.1.0
- Support for stream completions

## Version 1.2.0
- Support for /stash /pop /list save points
- Support for /clear and /reset
- Support for /tempurature and /frequency_penelty

## Version 1.3.0
- Support for /import (.md, .txt, .js, .cs, .java, .py, json, .yaml, .php, .csv, .json)
- Support for drop down commands selection
- Auto save point

## Version 1.4.0
- Section 508 support
- Mobile support (some issues)
- Support for CTRL+SHIFT+UP cycle through save points
- Support for CTRL+S to save content to a file

## Version 1.5.0
- Support for /model dall-e-3

## Version 1.6.0
- Medium refactor to to support other AI providers. I don't have any AI keys to try them, if I do, I will add support. I am unlikely to provide support for any Google/Alphabet models. I am in the process og a google-ectomy and would prefer not to support any of the google products. It all started last year when I wanted to use google APIs to get access to my tasks and notes. A long story short, it was very frustrating.

## Version 1.6.1
- Minor UX changes

## Version 1.7.0
- Added image to text processing
  - Optical Character Recognition (OCR) support using the Tesseract library
- Added PDF to text processing
  - PDF processing using PDF LIb and PDF JS
- Android closed testing

## Version 1.7.1
- Bug fixes and UX

## Version 1.7.2
- CLI and RobodogLib npm package. 
  npm install - 

## Version 2.0.0
- Support for multiple providers llamaAI and openAI
- Yaml configuration


## Roadmap 
- OCR support for Android
- VSCode extension

# Features

Robodog AI Assistant provides a flexible runtime, allowing installation on a laptop, Github pages, or a personal static file server without the need to install npm or run a node server. The webpack build generates two files, compiling them into a single HTML file named `robodog.html` and a JavaScript bundle called `robotdog.bundle.js`. Additionally, the tool does not require npm installation as it simply prompts for the API key, which is stored in local storage.

All chat history is conveniently accumulated in the 'chat context' text box, ensuring seamless continuation of conversations with the GPT AI. The feature allows users to add or remove chat contexts as needed. Users can also incorporate their knowledge, code, or documents for AI assistance and pose questions for optimized interactions.

Furthermore, users can effortlessly switch between GPT3.5 and GPT4 models without losing their chat context, enabling them to validate their questions and answers on a different model. Additionally, the system allows flexibility in choosing between cost-effective and higher-priced models, ensuring diverse options for tailored AI interactions.


![Screenshot](screenshot.png)

# Architecture

![Screenshot](screenshot-architecture.png)

![Screenshot](screenshot-architecture2.png)

# Create an API Key

Create an Open AI account and generate [new secret key](https://platform.openai.com/api-keys)

# Responsive

The UI is responsive and will work on a phone. You can use the GitHub pages link [Robodog](https://adourish.github.io/robodog/robodog/dist/)

![Mobile](mobile.png)

# Dall-e-

Dall-e-3 is supported

![Mobile](screenshot3dalle3.png)

# Accessibility

The UX was developed with section [508](https://www.section508.gov/) and [web accessibility](https://www.w3.org/WAI/fundamentals/accessibility-intro/) in mind. All of the actions (e.g., /clear, /gpt-4, /rest /help) can be executed from the chat window without navigating a menu. I have validated the UI using the [Wave tool](https://wave.webaim.org/.), but I have not tested the UX with a screen reader like [Jaws](https://www.freedomscientific.com/products/software/jaws/). I am confident that the UX should work for the /rest mode; the/stream mode will not work. If one single person messages me and has a need for an accessible GPT client, I will play around with the Aria tags and make /stream mode accessible.

# How it works

The chat/question is linked to the chat history and knowledge text areas.  
```
 const _messages = [
    { role: "user", content: "chat history:" + context },
    { role: "user", content: "knowledge:" + knowledge  },
    { role: "user", content: "question:" + text + ". Use the content in knowledge and chat history to answer the question." }
  ];
```
# Import

Use the /import command to open a file picker. You can select one or more files and they will be imported into the knowledge text area. You can use the /export feature to dump the content of your knowledge into a file.
 
![Features](import.png)

# Indicators

Use the char, rest, stream, status sloth/ape indicators to streamline your experience. 

- [0/9000][gpt-3.5-turbo][0.7][stream][🦥][🐁][][]

- [3432/9000] - estimated remaining context + knowledge + chat
- [gpt-3.5-turbo] - GPT model
- [0.7] - tempurature - larger numbers promote more creativity and are more prone to hallucination
- [rest] - rest completion mode
- [stream] - stream completion mode
- [🦥] - ready
- [🦧] - thinking
- [gpt-3.5-turbo-1106] - GPT model
- [🐋] - 💬📝💭 is dangerously large. Good luck to you.
- [🦕] - 💬📝💭 is very large.
- [🐘] - 💬📝💭 is large.
- [🐁] - 💬📝💭 is acceptable.

# Emoji

Role Emojis:
- 👾 - User
- 🤖 - Assistant
- 💾 - System
- 👹 - Event
- 💩 - Error
- 🍄 - Warning
- 😹 - Info
- 💣 - Experiment
- 🙀 - Default

Status Emojis:
- 🦥 - Ready
- 🦧 - Thinking
- 🐋 - Dangerously large
- 🦕 - Very large
- 🐘 - Large
- 🐁 - Acceptable

Performance Emojis: 
- 🐢 - Tortoise - longer than 20 seconds
- 🦅 - Hourglass - less than 1 second or more than 5 seconds
- 🦘 - Kangaroo
- 🐆 - Leopard
- 🦌 - Deer
- 🐕 - Dog
- 🐅 - Tiger
- 🐈 - Cat

Other Emojis:
- 💭 - Chat History
- 📝 - Knowledge Content
- 💬 - Chat Text


![Features](screenshot2.png)


## Stash, pop, and list

Switch chat contexts using the stash, pop, and list commands.

-   /stash <name> - stash 💬📝💭.
-   /pop <name> - pop 💬📝💭.
-   /list - list of stashed 💬📝💭.

![Mobile](stash.png)

## Menu

Use the drop down menu to select options.

![Features](menu.png)

## Optical Character Recognition (OCR) support using the Tesseract library

Optical Character Recognition (OCR) is the process that converts an image of text into a machine-readable text format. For example, if you scan a form or a receipt, your computer saves the scan as an image file. You cannot use a text editor to edit, search, or count the words in the image file.

- image-to-text using Tesseract
- text-to-image using dall-e-3

![Features](screenshot-ocr.png)

# Build

-   cd robodog
-   npm install
-   npm install openai
-   npm install zip-webpack-plugin
-   npm install pdfjs-dist
-   npm install axios
-   npm run build

# Run

-   Open in a `.\dist\robodog.html` in a browser.

# Commands

-   /gpt-3.5-turbo - switch to gpt-3.5-turbo-1106 model (4,096 tokens)(default).
-   /gpt-3.5-turbo-16k - switch to gpt-3.5-turbo-16k model (16,385 tokens).
-   /gpt-3.5-turbo-1106 - switch to gpt-3.5-turbo-1106 model (16,385 tokens).
-   /gpt-4 - switch to gpt-4 model (8,192 tokens).
-   /gpt-4-1106-preview - switch to gpt-4-1106-preview model (128,000 tokens).
-   /model <name> - set to a specific model.
-   /model dall-e-3
-   /help - get help.
-   /import - import files into knowledge (.md, .txt, .pdf, .js, .cs, .java, .py, json, .yaml, .php, .csv, .xsql, .json, .xml).
-   /export <filename> - export knowledge to a file.
-   /clear - clear 💬📝💭.
-   /rest - use rest completions.
-   /toggle - toggle context and knowledge text areas
-   /stream - use stream completions (default).
-   /reset - Reset your API key.
-   /stash <name> - stash 💬📝💭.
-   /pop <name> - pop 💬📝💭.
-   /list - list of stashed 💬📝💭.
-   /temperature 0.7 - If your use case allows for high variability or personalization (such as product recommendations) from user to user, we recommend a temperature of 0.7 or higher. For more static responses, such as answers to FAQs on return policies or shipping rates, adjust it to 0.4. We’ve also found that with a higher temperature metric, the model tends to add 10 to 15 words on top of your word/token limit, so keep that in mind when setting your parameters.
-   /max_tokens 500 - for short, concise responses (which in our experience is always best), choose a value between 30 and 50, depending on the main use cases of your chatbot.
-   /top_p 1 - recommend keeping this at 1, adjusting your temperature instead for the best results.
-   /frequency_penalty 0 - determine how often the same words appear in the chatbot’s response.Keep at 0.
-   /presence_penalty 0 - determine how often the same words appear in the chatbot’s response. Keep at 0.
-   SHIFT+UP - cycle through stash list.
-   CTRL + S - saSave a snapshot to storage
# Try

-   [Robodog](https://adourish.github.io/robodog/robodog/dist/)

# Download

-   [Download Robodog](https://github.com/adourish/robodog/tree/main/robodog/dist/robodog.zip)
