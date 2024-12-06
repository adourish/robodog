import express from 'express';
import axios from 'axios';
import RobodogLib from '../../robodoglib/dist/robodoglib.bundle.js';

const fileService = new RobodogLib.FileService();
const app = express();
app.use(express.json()); // For parsing application/json

class ConsoleCli {

    constructor() {
        this.hostname = 'localhost';
        this.port = 2500;
        this.app = express();
        this.configureRoutes();
    }

    configureRoutes() {
        this.app.post('/api/sendMessage', (req, res) => {
            const message = req.body;
            // send message
            const result = this.sendMessage(message);
            res.send(result);
        });

        this.app.get('/api/getMessage', async (req, res) => {
            // get message
            const message = await this.getMessage();
            res.send(message);
        });

        this.app.listen(this.port, () => {
            console.log(`Server running on http://${this.hostname}:${this.port}`);
        });
    }

    sendMessage(message) {
        fileService.write(message); // replace this with your actual logic
        return { "status" : "message sent"};
    }

    getMessage() {
        const message = fileService.read(); // replace this with your actual logic
        return message;
    }
}

export { ConsoleCli };

const consoleCli = new ConsoleCli();