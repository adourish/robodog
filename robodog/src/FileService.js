import FormatService from './FormatService';

// Define your extractMarkdownContent function
function extractMarkdownContent(file) {
  return new Promise((resolve, reject) => {
    const decoder = new TextDecoder('utf-8');
    const text = decoder.decode(file);
    resolve(text);
  });
}

// ... Rest of your code ...

async function extractFileContent(setContent, content) {
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.md, .txt, .pdf';
  setContent([
    ...content,
    FormatService.getMessageWithTimestamp(fileInput.name, 'assistant')
  ]);

  return new Promise((resolve, reject) => {
    fileInput.addEventListener('change', async () => {
      const file = fileInput.files[0];
      const reader = new FileReader();

      reader.onload = async (event) => {
        const content = event?.target?.result;
        if (file.type === 'application/pdf') {
          try {
            const pdfText = await extractPDFContent(content);
            resolve(pdfText);
          } catch (error) {
            reject('Error processing PDF content');
          }
        } else if (file.type === 'text/plain') {
          const text = extractTextContent(content);
          resolve(text);
        } else if (file.name.endsWith('.md') || file.type === 'text/markdown') {
          const markdownText = await extractMarkdownContent(content);
          resolve(markdownText);
        } else {
          reject('Invalid file format. Please select a PDF, text, or markdown file.');
        }
      };

      reader.onerror = () => {
        reject('Error reading file');
      };

      if (file.type === 'application/pdf' || file.type === 'text/plain' || file.type === 'text/markdown') {
        reader.readAsArrayBuffer(file);
      } else {
        reject('Invalid file format. Please select a PDF, text, or markdown file.');
      }
    });

    fileInput.click();
  });
}

export default { extractFileContent };
