import { StorageService } from './StorageService'
const storageService = new StorageService();

class RTCService {
    constructor() {
        console.debug('RTCService init')
        this.id = this.getNewId();
        console.debug('RTCService construct', this.id);
        
        
    }

    getConfiguration(){
        const configuration = {
            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
        };
        return configuration;
    }
    createDataChannel(channel){
        let configuration = this.getConfiguration();
        this.peerConnection = new RTCPeerConnection(configuration);
        this.dataChannel = this.peerConnection.createDataChannel(channel);
        this.peerConnection.onicecandidate = async ({ candidate }) => {
            console.debug('RTCService new onicecandidate', candidate);
            if (candidate) {
                try {
                    if (this.peerConnection && this.peerConnection.remoteDescription && this.peerConnection.remoteDescription.type) {
                        await this.peerConnection.addIceCandidate(candidate);
                    } else {
                        // Queue up the candidate if remoteDescription is not set.
                        this.queuedCandidates = this.queuedCandidates || [];
                        this.queuedCandidates.push(candidate);
                    }
                } catch (error) {
                    console.error('RTCService: Error adding ICE candidate', error);
                }
            }
        };
        return this.dataChannel;
    }

    getNewId(){
        // Get browser info
        const userAgent = window.navigator.userAgent;
        const browserInfo = userAgent.match(/(opera|chrome|safari|firefox|msie|trident(?=\/))\/?\s*(\d+)/i) || [];
        const browser = browserInfo[1];
        const version = browserInfo[2];

        // Get platform info
        const platform = window.navigator.platform;

        // Generate a unique id using browser and platform info
        let id = `${browser}_${version}_${platform}_${Math.random().toString(16).slice(2)}`;
        return id;
    }
    async isOpen() {
        try {
            if(this.dataChannel.readyState !== 'open'){
                await this.createOffer();
            }
            return this.dataChannel.readyState === 'open';
        } catch (error) {
            console.error('RTCService: Error checking/opening connection', error);
            return false;
        }        
    }


    async createOffer() {
        console.debug('RTCService createOffer');
        const offer = await this.peerConnection.createOffer({
            // Add the unique id to the offer's options
            offerToReceiveAudio: 1,
            offerToReceiveVideo: 1,
            iceRestart: true,
            voiceActivityDetection: false,
            id: this.id
        });
        await this.peerConnection.setLocalDescription(offer);
        return offer;
    }

    async handleAnswer(answer) {
        console.debug('RTCService handleAnswer', answer);
        await this.peerConnection.setRemoteDescription(answer);
    
        // Add any queued candidates (if any)
        if (this.queuedCandidates) {
            for (let candidate of this.queuedCandidates) {
                await this.peerConnection.addIceCandidate(candidate);
            }
            this.queuedCandidates = null; // Clear the queue
        }
    }

    async handleOffer(offer) {
        console.debug('RTCService handleOffer', offer);
        await this.peerConnection.setRemoteDescription(offer);
    
        // Add any queued candidates (if any)
        if (this.queuedCandidates) {
            for (let candidate of this.queuedCandidates) {
                await this.peerConnection.addIceCandidate(candidate);
            }
            this.queuedCandidates = null; // Clear the queue
        }
    
        // Get the unique id from the offer
        const id = offer.id;
        console.debug(`Received offer from RTCService with id: ${id}`);
    
        const answer = await this.peerConnection.createAnswer();
        await this.peerConnection.setLocalDescription(answer);
        return answer;
    }

    async send(message) {
        console.debug('RTCService message', message);
        if(await this.isOpen()){
            this.dataChannel.send(message);
        } else {
            console.error('RTCService: Connection is not open. Failed to send message:', message);
        }
    }

}

export { RTCService };