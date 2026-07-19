class ControlService {

  constructor(key = 'windows') {
    this.windows = this.getWindows(key);
  }

  getWindows(key = 'windows') {
    try {
      console.debug('getWindows new map')
      return new Map();

    } catch (error) {
      console.error('Failed to getWindows', error);
      return new Map();
    }
  }

  createWindow(url = '', width, height, left, top, name = 'Popup', focused = true, fullscreen = false, key = 'windows') {
    try {
      const existingWindow = this.windows.get(name);
      if (existingWindow) {
        console.debug('createWindow existing', name, existingWindow);

        existingWindow.document.title = name;
        this.setFullScreen(name, fullscreen);
        existingWindow.onload = function () { // Add this line
          console.debug('createWindow onload existing', name, newWindow)
          newWindow.document.title = name;
          this.setFullScreen(name, fullscreen);
          if (focused) {
            console.debug('createWindow focus existing', name, newWindow)
            newWindow.focus();
          }
        }
        if (focused) {
          console.debug('createWindow focus existing', name, newWindow)
          existingWindow.focus();
        }
        existingWindow.location.href = url;
      } else {
        console.debug('createWindow new v1', name)

        const features = `width=${width},height=${height},left=${left},top=${top}`;
        const newWindow = window.open(url, name, features);
        if (newWindow === null || newWindow === undefined) {
          throw new Error('Failed to create a new window');
        }
        this.windows.set(name, newWindow);

        try {
          newWindow.onload = function () {
            console.debug('foc newWindow.onload', name)
            // Add null checks before accessing properties or methods
            if (newWindow && newWindow.document) {
              newWindow.document.title = name;
              this.setFullScreen(name, fullscreen);
              if (focused) {
                console.debug('createWindow focus new ', name, newWindow)
                newWindow.focus();
              }
            }
          }

        } catch (error) {
          console.error('Failed to set properties on the new window', error);
        }
        this.setFullScreen(name, fullscreen);
        if (focused) {
          console.debug('createWindow focus new', name, newWindow)
          newWindow.focus();
        }
        newWindow.location.href = url;
        this.setWindowTitle(newWindow, name);
      }
    } catch (error) {
      console.error('Failed to create or focus on the window', error);
    }
  }

  setWindowTitle(newWindow, name) {
    setTimeout(function() {
      console.debug('createWindow setTimeout new', name, newWindow)
      if (newWindow && newWindow.document) {
        newWindow.document.title = name;
      }
    }, 3000);
  }

  focus(name = 'Popup') {
    try {
      console.debug('focus', name)
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
      console.debug('resizeWindow', name, width, height)
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
      console.debug('closeWindow', name)
      const existingWindow = this.windows.get(name);
      if (existingWindow) {
        existingWindow.close();
        this.windows.delete(name);
      }
    } catch (error) {
      console.error('Failed to close the window', error);
    }
  }

  setFullScreen(name = 'Popup', fullscreen = false) {
    try {
      console.debug('setFullScreen', name)
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