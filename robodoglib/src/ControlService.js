class ControlService {

  constructor() {
    this.windows = new Map();
  }
  createWindow(url = '', width, height, left, top, name = 'Popup', focused=true, fullscreen=false) {
    try {
      const existingWindow = this.windows.get(name);
      if (existingWindow) {
        console.debug('createWindow existing', existingWindow, url, name, width, height, left, focused)
        existingWindow.location.href = url;
        this.setFullScreen(name, fullscreen);
        existingWindow.focus();
      } else {
        console.debug('createWindow existing', url, name, width, height, left, focused)
        const features = `width=${width},height=${height},left=${left},top=${top}`;
        const newWindow = window.open(url, name, features);
        if (newWindow === null) {
          throw new Error('Failed to create a new window');
        }
        this.windows.set(name, newWindow);
        newWindow.location.href = url;
        this.setFullScreen(name, fullscreen);
        if (focused) {
          newWindow.focus();
        }
      }
    } catch (error) {
      console.error('Failed to create or focus on the window', error);
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
  
  setFullScreen(name = 'Popup', fullscreen=false) {
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