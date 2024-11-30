class ControlService {

  constructor(key = 'windows') {
    this.windows = this.getWindowInfoFromLocalStorage(key);
  }

  getWindowInfoFromLocalStorage(key = 'windows') {
    try {
      const windowInfo = localStorage.getItem(key);
      return windowInfo ? new Map(JSON.parse(windowInfo)) : new Map();
    } catch (error) {
      console.error('Failed to get windows from local storage', error);
      return new Map();
    }
  }

  saveWindowInfoToLocalStorage(key = 'windows') {
    try {
      const windowInfoArray = Array.from(this.windows.entries()).map(([name, {url}]) => [name, {url}]);
      localStorage.setItem(key, JSON.stringify(windowInfoArray));
    } catch (error) {
      console.error('Failed to save windows to local storage', error);
    }
  }

  createWindow(url = '', width, height, left, top, name = 'Popup', focused = true, fullscreen = false, key = 'windows') {
    try {
      const existingWindowInfo = this.windows.get(name);
      if (!existingWindowInfo) {
        console.debug('Creating new window', url, name, width, height, left, focused)
        const features = `width=${width},height=${height},left=${left},top=${top}`;
        const newWindow = window.open(url, name, features);
        if (newWindow === null) {
          throw new Error('Failed to create a new window');
        }
        // Save window information, not the window object itself
        this.windows.set(name, {url});
        newWindow.location.href = url;
        newWindow.document.title = name;
        this.setFullScreen(newWindow, fullscreen);
        if (focused) {
          newWindow.focus();
        }
        this.saveWindowInfoToLocalStorage(key);
      } else {
        console.debug('Window already exists', existingWindowInfo, url, name, width, height, left, focused)
        // Refresh the existing window instead of opening a new one
        const existingWindow = window.open(existingWindowInfo.url, name);
        existingWindow.focus();
      }
    } catch (error) {
      console.error('Failed to create or focus on the window', error);
    }
  }
  focus(name = 'Popup') {
    try {
      const existingWindow = this.windows.get(name);
      console.debug('focus', existingWindow, name)
      if (existingWindow) {
        existingWindow.focus(name);
      } else {

      }
    } catch (error) {
      console.error('Failed to resize the window', error);
    }
  }

  resizeWindow(name = 'Popup', width, height) {
    try {
      const existingWindow = this.windows.get(name);
      if (existingWindow) {
        existingWindow.resizeTo(width, height);
      }
    } catch (error) {
      console.error('Failed to resize the window', error);
    }
  }

  setFullScreen(name = 'Popup', fullscreen = false) {
    try {
      const existingWindow = this.windows.get(name);
      if (existingWindow && fullscreen) {
        existingWindow.document.documentElement.requestFullscreen(); // Enable fullscreen
      }
    } catch (error) {
      console.error('Failed to set the window to fullscreen', error);
    }
  }
  runScriptOnWindow(name, code) {
    try {
      const existingWindow = this.windows.get(name);
      if (existingWindow) {
        const script = document.createElement('script');
        script.textContent = code;
        existingWindow.document.body.appendChild(script);
      }
    } catch (error) {
      console.error('Failed to run the script on the window', error);
    }
  }
}

export { ControlService };