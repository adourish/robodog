function getMessageWithTimestamp(command, role) {
    const options = { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' };
    const shortTimeString = new Date().toLocaleTimeString(undefined, options);
  
    let roleEmoji;
    switch (role) {
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
      //experiment
      case 'experiment':
        roleEmoji = '💣';
        break;
      default:
        roleEmoji = '🙀';
    }
    return `${shortTimeString}${roleEmoji}: ${command}`;
  }

  export default { getMessageWithTimestamp };