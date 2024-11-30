class ControlService {

  constructor(key = 'windows') {
    this.windows = this.getWindowsFromLocalStorage(key);
  }

  getWindowsFromLocalStorage(key = 'windows') {
    try {
      const queryString = new URLSearchParams(window.location.search);
      const windowNames = queryString.get(key);
      if (windowNames) {
        const windowNamesArray = windowNames.split(",");
        return new Map(windowNamesArray.map(name => {
          if (!queryString.get(name)) {
            return [name, null];
          }
          return [name, queryString.get(name)];
        }));
      } else {
        return new Map();
      }
    } catch (error) {
      console.error('Failed to get windows from local storage', error);
      return new Map();
    }
  }

  createWindow(url = '', width, height, left, top, name = 'Popup', focused = true, fullscreen = false, key = 'windows') {
    try {
      const existingWindow = this.windows.get(name);
      if (existingWindow) {
        existingWindow.location.href = url;
        existingWindow.document.title = name;
        this.setFullScreen(name, fullscreen);
        existingWindow.focus();
      } else {
        // Avoid creating a new window if it's already in the query string
        const queryString = new URLSearchParams(window.location.search);
        if (!queryString.get(name)) {
          const features = `width=${width},height=${height},left=${left},top=${top}`;
          const newWindow = window.open(url, name, features);
          if (newWindow === null) {
            throw new Error('Failed to create a new window');
          }
          this.windows.set(name, newWindow);
          newWindow.location.href = url;
          newWindow.document.title = name;
          this.setFullScreen(name, fullscreen);
          if (focused) {
            newWindow.focus();
          }
          // Add the new window to the query string
          queryString.set(name, '');
          window.history.replaceState(null, "", "?" + queryString.toString());
          this.saveWindowsToLocalStorage();
        }
      }
    } catch (error) {
      console.error('Failed to create or focus on the window', error);
    }
  }


  saveWindowsToLocalStorage(key = 'windows') {
    try {
      const queryString = new URLSearchParams(window.location.search);
      const windowNames = Array.from(this.windows.keys()).join(",");
      queryString.set(key, windowNames);
      window.history.replaceState(null, "", "?" + queryString.toString());
    } catch (error) {
      console.error('Failed to save windows to local storage', error);
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

  closeWindow(name = 'Popup') {
    try {
      const existingWindow = this.windows.get(name);
      if (existingWindow) {
        existingWindow.close();
        this.windows.delete(name);
        this.saveWindowsToLocalStorage();
      }
    } catch (error) {
      console.error('Failed to close the window', error);
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