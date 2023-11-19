import { PDFDocument } from 'pdf-lib';
function extractFileContent() {
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.md, .txt, .pdf';

  return new Promise((resolve, reject) => {
    fileInput.addEventListener('change', async () => {
      const file = fileInput.files[0];
      const reader = new FileReader();

      reader.onload = async (event) => {
        const content = event.target.result;
        if (file.type === 'application/pdf') {
          try {
            const pdfDoc = await PDFDocument.load(new Uint8Array(content));
            const pages = pdfDoc.getPages();
            let pdfText = '';
            for (const page of pages) {
              const pageText = await page.getTextContent();
              pdfText += pageText.items.map((item) => item.str).join(' ');
            }
            resolve(pdfText);
          } catch (error) {
            reject('Error processing PDF content');
          }
        } else if (file.type === 'text/plain') {
          const decoder = new TextDecoder('utf-8');
          const text = decoder.decode(content);
          resolve(text);
        } else if (file.type === 'text/markdown') {
          const decoder = new TextDecoder('utf-8');
          const text = decoder.decode(content);
          resolve(text);
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