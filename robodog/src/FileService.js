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
async function handleFileInputChange(fileInput, resolve, reject) {
  const file = fileInput.files[0];

  if (!file) {
    reject('No file selected');
    return;
  }

  var reader = null;
  try {
    reader = new FileReader();

    reader.onload = async (event) => {
      try {
        const arrayBuffer = event.target.result;
        console.error(file);
        switch (file.type) {
          case 'application/pdf':
            try {
              const pdfText = await extractPDFContent(file.name, arrayBuffer);
              resolve(pdfText);
            } catch (error) {
              reject('Error processing PDF content');
            }
            break;
          case 'text/plain':
          case 'text/markdown':
            var t = extractTextContent(arrayBuffer);
            resolve(file.name + ":\n" + t);
            break;
          default:
            console.error(file);
            if (file.name.endsWith('.md') || file.name.endsWith('.txt') || file.name.endsWith('.pdf') || file.name.endsWith('.js') || file.name.endsWith('.cs') || file.name.endsWith('.java') || file.name.endsWith('.py') || file.name.endsWith('.json') || file.name.endsWith('.yaml') || file.name.endsWith('.php')) {
              var t = extractTextContent(arrayBuffer);
              resolve(file.name + ":\n" + t);
            } else {
              reject('Invalid file format. Please select a supported file format.');
            }

        }
      } catch (error) {
        reject('Error processing file content');
      }
    };

    reader.onerror = () => {
      console.error(reader.error);
      reject('Error reading file');
    };

    reader.readAsArrayBuffer(file);
  } catch (ex) {
    console.error(ex);
  }
}

async function extractFileContent(setContent, content) {
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = fileFormats;

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