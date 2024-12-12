import axios from 'axios';

class HostService {
    constructor() {
        this.hostname = 'localhost';
        this.port = 2500;
        this.failureCount = 0;
        this.failureThreshold = 3; // Will break after 3 failures
        this.retryTime = 5 * 60 * 1000; // Will wait for 5 minutes before next attempt
        this.lastAttemptTime = null;
        this.circuitBreakerEnabled = true; 
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
    
    toggleCircuitBreaker(enabled) {
        this.circuitBreakerEnabled = enabled;
        console.debug(`Circuit breaker ${this.circuitBreakerEnabled ? 'enabled' : 'disabled'}`);
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
                throw new Error('Failed to send message');
            });
    }
    
    getMessage() {
        if(this.circuitBreakerEnabled === false){
            console.debug('HostService.getMessage Service disabled ', this.circuitBreakerEnabled);
            return null;
        }
        else if (this.failureCount >= this.failureThreshold &&
            new Date().getTime() - this.lastAttemptTime < this.retryTime) {
            console.debug('HostService.getMessage Service temporarily unavailable due to failure threshold reached');
            return null;
        }
        return axios.get(`http://${this.hostname}:${this.port}/api/getMessage`)
            .then(response => {
                console.debug('HostService.getMessage Message received:', response.data);
                this.failureCount = 0;
                return response.data;
            })
            .catch(error => {
                console.debug('HostService.Error receiving message:', error);
                this.failureCount += 1;
                this.lastAttemptTime = new Date().getTime();
                throw new Error('Failed to get message');
            });
    }
    
    getGroups() {
        return axios.get(`http://${this.hostname}:${this.port}/api/getGroups`)
            .then(response => {
                console.debug('HostService.getGroups Groups received:', response.data);
                return response.data;
            })
            .catch(error => {
                console.debug('HostService.Error getting groups:', error);
                throw new Error('Failed to get groups');
            });
    }
    
    setActiveGroup(group) {
        const encodedGroup = encodeURIComponent(group);
        return axios.get(`http://${this.hostname}:${this.port}/api/activateGroup/${encodedGroup}`)
            .then(response => {
                console.debug('HostService.setActiveGroup Group set:', response.data);
                return response.data;
            })
            .catch(error => {
                console.debug('HostService.Error setting active group:', error);
                throw new Error('Failed to set active group');
            });
    }
    
    setActiveFile(file) {
        const encodedFile = decodeURIComponent(file);
        return axios.get(`http://${this.hostname}:${this.port}/api/activateFile/${encodedFile}`)
            .then(response => {
                console.debug('HostService.setActiveFile File set:', response.data);
                return response.data;
            })
            .catch(error => {
                console.debug('HostService.Error setting active file:', error);
                throw new Error('Failed to set active file');
            });
    }
}

export { HostService };