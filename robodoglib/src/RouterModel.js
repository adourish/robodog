
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
        setContent =null,
        setContext = null,
        setMessage = null,
        setThinking = null,
        setPerformance = null,
        setKnowledge = null
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
        this.setContent = setContent;
        this.setContext = setContext;
        this.setMessage = setMessage;
        this.setThinking = setThinking;
        this.setPerformance = setPerformance; 
        this.setKnowledge = setKnowledge;
    }
}

export { RouterModel };