import FormatService from './FormatService';

// Extracts content from a text or markdown file
function extractTextContent(arrayBuffer) {
  const decoder = new TextDecoder('utf-8');
  return decoder.decode(arrayBuffer);
}

// Extracts content from a PDF file
async function extractPDFContent(arrayBuffer) {
  // Placeholder for actual PDF extraction logic
  // Replace this with your actual PDF content extraction method
}

// Handles file input change event
async function handleFileInputChange(fileInput, resolve, reject) {
  const file = fileInput.files[0];

  if (!file) {
    reject('No file selected');
    return;
  }

  const reader = new FileReader();

  reader.onload = async (event) => {
    try {
      const arrayBuffer = event.target.result;

      switch (file.type) {
        case 'application/pdf':
          try {
            const pdfText = await extractPDFContent(arrayBuffer);
            resolve(pdfText);
          } catch (error) {
            reject('Error processing PDF content');
          }
          break;
        case 'text/plain':
        case 'text/markdown':
          resolve(extractTextContent(arrayBuffer));
          break;
        default:
          reject('Invalid file format. Please select a PDF, text, or markdown file.');
      }
    } catch (error) {
      reject('Error processing file content');
    }
  };

  reader.onerror = () => reject('Error reading file');
  reader.readAsArrayBuffer(file);
}

// Main function to extract content from file
async function extractFileContent(setContent, content) {
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.md, .txt, .pdf';

  setContent([
    ...content,
    FormatService.getMessageWithTimestamp(fileInput.name, 'assistant')
  ]);

  return new Promise((resolve, reject) => {
    fileInput.addEventListener('change', () => handleFileInputChange(fileInput, resolve, reject));
    fileInput.click();
  });
}

export default { extractFileContent };
