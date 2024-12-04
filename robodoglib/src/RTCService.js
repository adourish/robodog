import { StorageService } from './StorageService';
const storageService = new StorageService();

class RTCService {
    constructor() {
        console.debug('RTCService init')

    }   

    getConfiguration() {
        let configuration = {'iceServers': [{'urls': 'stun:stun.l.google.com:19302'}]}
        return configuration;
    }

    getDataChannel(){
        return new Promise((resolve, reject) => {
            try {
                const peerConnection = new RTCPeerConnection(configuration);
                const dataChannel = peerConnection.createDataChannel('robodog-knowledge-channel');
                console.debug('Data channel created');
                resolve(dataChannel);
            } catch (error) {
                console.error('Error creating data channel:', error);
                reject(error);
            }
        });
    }

    sendMessage(message){
        return new Promise((resolve, reject) => {
            try {
                let dataChannel = this.getDataChannel();
                dataChannel.send(message);
                console.debug('Message sent:', message);
                resolve();
            } catch (error) {
                console.error('Error sending message:', error);
                reject(error);
            }
        });
    }

    getMessage(){
        return new Promise((resolve, reject) => {
            try {
                let dataChannel = this.getDataChannel();
                dataChannel.addEventListener('message', event => {
                    const message = event.data;
                    incomingMessages.textContent += message + '\n';
                    console.debug('Message received:', message);
                    resolve(message);
                });
            } catch (error) {
                console.error('Error receiving message:', error);
                reject(error);
            }
        });
    }
}

export { RTCService };