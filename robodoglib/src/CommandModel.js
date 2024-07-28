class Callbacks {
    constructor() {
        this.setContent = () => { };
        this.setContext = () => { };
        this.setMessage = () => { };
        this.setThinking = () => { };
        this.setPerformance = () => { };
    }
}

class CommandModel {
    constructor(
        command = "",
       
        callbacks = new Callbacks()
    ) {
        this.command = command;

        this.callbacks = callbacks;
    }
}

export { RouterModel };