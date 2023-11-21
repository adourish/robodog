import FormatService from './FormatService';

function extractTextContent(arrayBuffer) {
  const decoder = new TextDecoder('utf-8');
  return decoder.decode(arrayBuffer);
}

async function extractPDFContent(arrayBuffer) {
  // Placeholder for actual PDF extraction logic
  // Replace this with your actual PDF content extraction method
}
const fileFormats = '.md, .txt, .pdf, .js, .cs, .java, .py, json, .yaml, .php';
async function handleFileInputChange(fileInput) {
  const files = fileInput.files;
  const fileCount = files.length;
  let importedCount = 0;
  let errorCount = 0;
  let resultText = "Importing:" + fileCount + " files...\n";

  for (let i = 0; i < fileCount; i++) {
    const file = files[i];
    try {
      const arrayBuffer = await readFile(file);
      resultText += "File: " + file.name + "\n```\n";
      switch (file.type) {
        case 'application/pdf':
          try {
            const pdfText = await extractPDFContent(file.name, arrayBuffer);
            resultText += pdfText;
            importedCount++;
          } catch (error) {
            resultText += "Error processing PDF content: " + error;
            errorCount++;
          }
          break;
        case 'text/plain':
        case 'text/markdown':
          const textContent = extractTextContent(arrayBuffer);
          resultText += file.name + ":\n" + textContent;
          importedCount++;
          break;
        default:
          if (isSupportedFileFormat(file.name)) {
            const textContent = extractTextContent(arrayBuffer);
            resultText += file.name + ":\n" + textContent;
            importedCount++;
          } else {
            resultText += "Invalid file format for " + file.name;
            errorCount++;
          }
      }
      resultText += "```\n";
    } catch (error) {
      resultText += file.name + ": " + error;
      errorCount++;
    }
  }

  resultText += "Imported:" + importedCount + " files successfully.";
  resultText += "\nFailed to import " + errorCount + " files.";

  return resultText;
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (event) => resolve(event.target.result);
    reader.onerror = (error) => reject(error);
    reader.readAsArrayBuffer(file);
  });
}

function isSupportedFileFormat(fileName) {
  const supportedFormats = ['.md', '.txt', '.pdf', '.js', '.cs', '.java', '.py', '.json', '.yaml', '.php', '.sql', '.xsql'];
  return supportedFormats.some((format) => fileName.endsWith(format));
}

async function extractFileContent(setContent, content) {
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = fileFormats;
  fileInput.multiple = true;
  setContent([
    ...content,
    FormatService.getMessageWithTimestamp(fileInput.name, 'assistant')
  ]);

  return new Promise((resolve, reject) => {
    fileInput.addEventListener('change', () => handleFileInputChange(fileInput).then(resolve).catch(reject));
    fileInput.click();
  });
}

export default { extractFileContent };