# Robodog AI Overview

## About


Robodog is a powerful and versatile generative AI client that provides comprehensive support for a diverse range of advanced models, including the cutting-edge `o4-mini` with enhanced reasoning capabilities, along with renowned options like `gpt-4`, `gpt-4-turbo`, and `dall-e-3`. The platform also integrates groundbreaking models from prominent AI providers, such as LlamaAI, DeepSeek, Anthropic's Claude, and Sarvam AI, making it the ideal solution for varied applications, including programming, healthcare, and creative tasks.

Robodog features an intuitive command-line interface, enabling seamless execution of commands like switching models, adjusting parameters, and managing chat contexts effortlessly. Users can utilize commands such as `/stash`, `/pop`, `/clear`, and `/list` to navigate, manage, and manipulate conversation histories easily, including adding or removing specific entries as needed. The platform boasts support for exceptionally large context buffers, accommodating up to 200k tokens, ensuring that extensive dialogue or input history is retained and accessible for meaningful interactions.

Moreover, Robodog allows users to create save points in their conversation history, enabling them to revert to previous states as necessary. The `/import` functionality lets users bring in files across multiple formats—such as markdown, plaintext, JSON, and programming languages—greatly enhancing the knowledge base and context available for interaction. Additionally, users can save their configurations in a YAML format, allowing for easy retrieval and management of settings.

Designed as a lightweight client, Robodog requires no installation, ensuring quick and hassle-free access. The platform excels in providing rich responses through its chat history management system, ensuring that every conversation is contextual and relevant. With built-in support for Optical Character Recognition (OCR), users can convert images to text and vice versa, empowering diverse content creation and analysis.

Whether you need sophisticated responses or creative outputs, Robodog empowers you to engage with AI efficiently and effectively, offering a comprehensive toolkit that meets the demands of any user scenario. Experience the future of AI interaction with Robodog, designed to adapt to your needs while delivering unparalleled performance.

Whether you need sophisticated responses or creative outputs, Robodog empowers you to engage with AI efficiently and effectively, offering a comprehensive toolkit that meets the demands of any user scenario. Experience the future of AI interaction with Robodog, designed to adapt to your needs while delivering unparalleled performance.

## Try Robodog

- **Web**: [Robodog web](https://adourish.github.io/robodog/robodog/dist/)
- **Android**: [Robodog Android](https://play.google.com/store/apps/details?id=com.unclebulgaria.robodog)
- **npm packages**:
  - [robodoglib](https://www.npmjs.com/package/robodoglib)
  - [robodogcli](https://www.npmjs.com/package/robodogcli)
  - [robodog](https://www.npmjs.com/package/robodog)

## Configuration

### Configuring Providers and Models

To configure the models and providers, click the ⚙️ icon.

![Configuration Settings](screenshot-quick.png)

### YAML Configuration Example

Here's a sample of YAML configuration:

```yaml
  
configs:
  providers:
    - provider: openAI
      baseUrl: "https://api.openai.com"
      apiKey: "<key>"
      httpReferer: "https://adourish.github.io"
    - provider: openRouter
      baseUrl: "https://openrouter.ai/api/v1"
      apiKey: "<key>"
      httpReferer: "https://adourish.github.io"
    - provider: searchAPI
      baseUrl: "https://google-search74.p.rapidapi.com"
      apiKey: "<key>"
      httpReferer: "https://adourish.github.io"
      
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
      model: dall-e-3
      stream: false
      specialist: gi
      about: best for creating images
    - provider: searchAPI
      model: search
      stream: false
      specialist: search
      about: best for searching
```

## Supported Models

Robodog supports a wide range of models provided by various major AI providers, including:

### OpenAI
- gpt-4
- gpt-3.5-turbo
- gpt-3.5-turbo-16k
- dall-e-3

### LlamaAI
- llama3-70b

### DeepSeek
- DeepSeek R1
- DeepSeek R1 (Free version)

### Anthropic
- Claude Opus 4
- Claude Sonnet 4

### Mistral
- Mistral Medium 3
- Mistral Devstral-Small 2505

### Sarvam AI
- Sarvam-M

### Google Models
- Gemma 3n E4B

## Features

### Key Features of Robodog
- **Supports Multiple Providers:** Users can switch between different AI providers.
- **File Import/Export:** Import files from various formats and export knowledge content.
- **Image Processing:** Support for OCR using the Tesseract library and image-to-text using Dall-E-3.
- **Chat History Management:** Utilize stash, pop, and list commands to manage chat contexts.
- **Flexible Runtime:** Install and run without needing npm or a node server.

### New Features
- **Mobile Support:** Responsive UI that works on mobile devices.
- **Batch Execution:** Execute batches of generative AI commands.
- **Stash Management:** Improved stash management using stash, pop, and list commands.

## How It Works

Robodog integrates chat history and knowledge into the questions posed:

```javascript
const _messages = [
    { role: "user", content: "chat history:" + context },
    { role: "user", content: "knowledge:" + knowledge  },
    { role: "user", content: "question:" + text + ". Use the content in knowledge and chat history to answer the question." }
];
```

### Syntax

• `/include all`  
• `/include file=*.txt` → glob search across all roots  
• `/include pattern=*zilla*.txt` → shorthand for a full‐roots search  
• `/include dir=temp pattern=*zilla*.txt recursive` → deep search under “temp/” folders,

> Note: patterns use Unix-style globs (`*`, `?`), not full regex.

### What Gets Injected

1. A SYSTEM message containing the full contents of each file, tagged with  
   ```  
   --- file: /path/to/file.ext ---  
   (file contents…)  
   ```  
2. A second SYSTEM message containing a brief summary of the included files:  
   ```  
   File: /path/to/file.ext (1234 bytes)  
   File: /another/path/foo.js (  87 bytes)  
   ```  
3. Your original user prompt is augmented with that summary.

### Examples

1. Include every file under your served roots:  
   ```
   /include all
   ```
2. Include exactly one markdown file (README.md must exist somewhere in your roots):  
   ```
   /include file=README.md
   ```
3. Include every JavaScript file in a single directory (non-recursive):  
   ```
   /include dir=src pattern=*.js
   ```
4. Include all Python files under `lib/` and its subdirectories:  
   ```
   /include dir=lib pattern=*.py recursive
   ```
5. Combine `/include` with a follow-up question:  
   ```
   /include dir=docs pattern=*.md recursive
   Please summarize the public API defined in these markdown files.
   ```

### Supported File Formats

Thanks to MCP, you can include any text-based file. Common examples:

• Markdown: `.md`, `.markdown`  
• Plain text: `.txt`, `.text`  
• JSON: `.json`  
• Source code: `.js`, `.ts`, `.py`, `.java`, `.c`, `.cpp`, `.go`, `.rs`  
• Configs & data: `.yaml`, `.yml`, `.xml`, `.csv`

Just adjust the `pattern=` glob to match the extensions you need.

## Import/Export Commands

Use the `/import` command to open a file picker and select files for import.

![Import Features](import.png)

You can use the `/export <filename>` command to dump the content of your knowledge into a file.

## Stash, Pop, and List Commands

Manage chat contexts efficiently:
- `/stash <name>` - Stash the current chat and knowledge.
- `/pop <name>` - Retrieve a stashed chat and knowledge.
- `/list` - List all stashed chats.

## Indicators

Use the following indicators for a streamlined experience:

- `[0/9000]` - Estimated remaining context + knowledge + chat
- `[gpt-3.5-turbo]` - Current model in use
- `[0.7]` - Temperature setting

## Emoji Indicators

### Role Emojis
- **User**: 👾
- **Assistant**: 🤖
- **System**: 💾
- **Event**: 👹
- **Error**: 💩

### Status Emojis
- **Ready**: 🦥
- **Thinking**: 🦧
- **Dangerous Size**: 🐋
- **Very Large Size**: 🦕
- **Large Size**: 🐘
- **Acceptable Size**: 🐁

### Performance Emojis
- **Tortoise**: 🐢
- **Kangaroo**: 🦘

![Architecture](screenshot-architecture.png)

## Accessibility

Robodog AI was developed with accessibility in mind, addressing Section 508 standards and web accessibility principles.

## Build and Run Instructions

To build and run Robodog:

```bash
cd robodog
python build.py
```

Open `./dist/robodog.html` in your browser to start using it.

### Summary

Robodog AI is a robust API client that combines the capabilities of various AI models and providers for diverse applications. With its interactive features and support for multiple data formats, it offers a flexible and efficient platform for engaging with AI technologies.