class FormatService {

  getRandomEmoji() {
    const emojis = ["🦉", "🐝", "🦧"];
    const index = new Date().getMilliseconds() % emojis.length;
    return emojis[index];
  }

  getTooBigEmoji(_totalChars, maxChars) {
    if (_totalChars >= maxChars) {
      return '🐋'; // Dinosaur emoji for the biggest level
    } else if (_totalChars >= (maxChars * 0.75)) {
      return '🦕'; // Bear emoji for the third level
    } else if (_totalChars >= (maxChars * 0.5)) {
      return '🐘'; // Lion emoji for the second level
    } else if (_totalChars >= (maxChars * 0.25)) {
      return '🐁'; // Mouse emoji for the first level
    }
  }
  
  getMessageWithTimestamp(command, role, url) {
    const options = { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' };
    const shortTimeString = new Date().toLocaleTimeString(undefined, options);

    let roleEmoji;
    switch (role) {
      case 'image':
        roleEmoji = '🖼';
        break;
      case 'user':
        roleEmoji = '👾';
        break;
      case 'assistant':
        roleEmoji = '🤖';
        break;
      case 'system':
        roleEmoji = '💾';
        break;
      case 'event':
        roleEmoji = '👹';
        break;
      case 'error':
        roleEmoji = '💩';
        break;
      case 'warning':
        roleEmoji = '🍄';
        break;
      case 'info':
        roleEmoji = '😹';
        break;
      case 'title':
        roleEmoji = '🛸';
        break;
      case 'ufo':
        roleEmoji = '🛸';
        break;
      case 'experiment':
        roleEmoji = '💣';
        break;
      default:
        roleEmoji = '🙀';
    }

    var item = {
      "datetime": `${shortTimeString}`,
      "role": role,
      "roleEmoji": `${roleEmoji}`,
      "command": `${command}`,
      "url": url,
      "focus": false
    };
    
    return item;
  }
}

export  { FormatService };