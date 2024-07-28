
class StorageService {
    constructor() {

    }

    removeItem(key) {
        localStorage.removeItem(key);
    }

    setItem(key, value) {
        console.debug('Set key', key)
        localStorage.setItem(key, value);
    }

    getItem(key) {
        const item = localStorage.getItem(key);
        return item;
    }
}
export { StorageService };