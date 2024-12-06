import axios from 'axios';

class HostService {
    constructor() {
        this.hostname = 'localhost';
        this.port = 2500;
        this.failureCount = 0;
        this.failureThreshold = 3; // Will break after 3 failures
        this.retryTime = 5 * 60 * 1000; // Will wait for 5 minutes before next attempt
        this.lastAttemptTime = null;
    }

    init(host, port, failureThreshold, retryTime){
        if (!host || !port) {
            throw new Error('Host and port must be defined');
        }
        this.hostname = host;
        this.port = port;
        this.failureThreshold = failureThreshold || this.failureThreshold;
        this.retryTime = retryTime || this.retryTime;
        
        console.debug(`HostService.Init called with parameters host: ${host}, port: ${port}, failureThreshold: ${failureThreshold}, retryTime: ${retryTime}`);
    }
    
    sendMessage(message) {
        if (!message) {
            throw new Error('HostService.sendMessage Message cannot be empty');
        }
        if (this.failureCount >= this.failureThreshold && 
            new Date().getTime() - this.lastAttemptTime < this.retryTime) {
            console.debug('HostService.sendMessage Service temporarily unavailable due to failure threshold reached');
            return null;
        }
        return axios.post(`http://${this.hostname}:${this.port}/api/sendMessage`, message)
            .then(response => {
                console.debug('HostService.sendMessage Message sent:', message);
                this.failureCount = 0;
                return response.data;
            })
            .catch(error => {
                console.debug('HostService.Error sending message:', error);
                this.failureCount += 1;
                this.lastAttemptTime = new Date().getTime();
                throw error;
            });
    }

    getMessage() {
        if (this.failureCount >= this.failureThreshold && 
            new Date().getTime() - this.lastAttemptTime < this.retryTime) {
            console.debug('HostService.sendMessage Service temporarily unavailable due to failure threshold reached');
            return null;
        }
        return axios.get(`http://${this.hostname}:${this.port}/api/getMessage`)
            .then(response => {
                console.debug('sendMessage Message received:', response.data);
                this.failureCount = 0;
                return response.data;
            })
            .catch(error => {
                console.debug('HostService.Error receiving message:', error);
                this.failureCount += 1;
                this.lastAttemptTime = new Date().getTime();
                throw error;
            });
    }
}

export { HostService };