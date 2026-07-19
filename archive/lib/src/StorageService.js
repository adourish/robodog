class StorageService {
    constructor() {
      this._inMemoryStore = {};
      this._localStorageAvailable = this._checkLocalStorage();
    }
  
    // Private: verify localStorage actually works
    _checkLocalStorage() {
      const testKey = "__storage_test__";
      try {
        window.localStorage.setItem(testKey, testKey);
        window.localStorage.removeItem(testKey);
        return true;
      } catch (e) {
        console.warn("localStorage unavailable, falling back to in-memory store.", e);
        return false;
      }
    }
  
    setItem(key, value) {
      const stringValue = typeof value === "string" ? value : JSON.stringify(value);
      if (!this._localStorageAvailable) {
        this._inMemoryStore[key] = stringValue;
        return;
      }
      try {
        window.localStorage.setItem(key, stringValue);
      } catch (e) {
        console.warn(`Failed to setItem(${key}) in localStorage, using in-memory.`, e);
        this._inMemoryStore[key] = stringValue;
        this._localStorageAvailable = false; // stop further attempts
      }
    }
  
    getItem(key) {
      if (!this._localStorageAvailable) {
        return this._inMemoryStore.hasOwnProperty(key)
          ? this._inMemoryStore[key]
          : null;
      }
      try {
        return window.localStorage.getItem(key);
      } catch (e) {
        console.warn(`Failed to getItem(${key}) from localStorage, reading in-memory.`, e);
        this._localStorageAvailable = false;
        return this._inMemoryStore.hasOwnProperty(key)
          ? this._inMemoryStore[key]
          : null;
      }
    }
  
    removeItem(key) {
      if (!this._localStorageAvailable) {
        delete this._inMemoryStore[key];
        return;
      }
      try {
        window.localStorage.removeItem(key);
      } catch (e) {
        console.warn(`Failed to removeItem(${key}) from localStorage, removing from in-memory.`, e);
        this._localStorageAvailable = false;
        delete this._inMemoryStore[key];
      }
    }
  
    clear() {
      if (!this._localStorageAvailable) {
        this._inMemoryStore = {};
        return;
      }
      try {
        window.localStorage.clear();
      } catch (e) {
        console.warn("Failed to clear localStorage, clearing in-memory store.", e);
        this._localStorageAvailable = false;
        this._inMemoryStore = {};
      }
    }
  }
  
  export { StorageService };