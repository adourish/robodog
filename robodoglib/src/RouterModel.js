class Callbacks {
    constructor() {
        this.setContent = () => { };
        this.setContext = () => { };
        this.setMessage = () => { };
        this.setThinking = () => { };
        this.setPerformance = () => { };
    }
}

class RouterModel {
    constructor(
        question = "",
        model = "",
        context = "",
        knowledge = "",
        content = "",
        temperature = 0,
        max_tokens = 0,
        currentKey = "",
        size = "1792x1024",
        callbacks = new Callbacks()
    ) {
        this.question = question;
        this.model = model;
        this.context = context;
        this.knowledge = knowledge;
        this.content = content;
        this.temperature = temperature;
        this.max_tokens = max_tokens;
        this.currentKey = currentKey;
        this.size = size;
        this.callbacks = callbacks;
    }
}

export { RouterModel };