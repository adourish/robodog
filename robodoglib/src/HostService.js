import axios from 'axios';

class HostService {
    constructor() {
        this.hostname = 'localhost';
        this.port = 2500;
    }

    init(host, post){
        if (!host || !post) {
            throw new Error('Host and port must be defined');
        }
        this.hostname = host;
        this.port = post;
    }
    
    sendMessage(message) {
        if (!message) {
            throw new Error('Message cannot be empty');
        }
        return axios.post(`http://${this.hostname}:${this.port}/api/sendMessage`, message)
            .then(response => {
                console.debug('Message sent:', message);
                return response.data;
            })
            .catch(error => {
                console.error('Error sending message:', error);
                throw error;
            });
    }

    getMessage() {
        return axios.get(`http://${this.hostname}:${this.port}/api/getMessage`)
            .then(response => {
                console.debug('Message received:', response.data);
                return response.data;
            })
            .catch(error => {
                console.error('Error receiving message:', error);
                throw error;
            });
    }
}

export { HostService };