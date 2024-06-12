function getMessageWithTimestamp(command, role, url) {
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
    case 'ufo':
      roleEmoji = '🛸';
      break;
    //experiment
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

export default { getMessageWithTimestamp };