import FormatService from './FormatService';
import pdfjs, { GlobalWorkerOptions, getDocument } from 'pdfjs-dist/es5/build/pdf';
import pdfjsWorker from 'pdfjs-dist/es5/build/pdf.worker.entry';
import Tesseract from 'tesseract.js';

GlobalWorkerOptions.workerSrc = pdfjsWorker;


async function extractTextContent(arrayBuffer) {
  console.debug('extractTextContent', arrayBuffer)
  const decoder = new TextDecoder('utf-8');
  return decoder.decode(arrayBuffer);
}


async function extractPDFContent(arrayBuffer) {
  GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.2.2/pdf.worker.js';


  console.debug('extractPDFContent', arrayBuffer);
  let text = '';
  try {
    let pdf = await getDocument({data: arrayBuffer}).promise;
    if (pdf) {
      console.debug(pdf);
      var pageCount = await pdf.numPages;
      if (pageCount) {

        for (let i = 1; i <= pageCount; i++) {
          let page = await pdf.getPage(i);
          if (page) {
            let content = await page.getTextContent();
            text += content.items.map(item => item.str).join(' ');
          }
        }

      }
    }
    return text;
  } catch (error) {
    console.error('An error occurred while extracting the PDF content', error);
    return 'error ' + error;
  }
}
async function extractImageContent(arrayBuffer) {
  console.debug('extractImageContent', arrayBuffer)
  var text = ''
  try {
    var r = await Tesseract.recognize(arrayBuffer, 'eng');
    console.debug('Tesseract.recognize', r)
    if (r.data && r.data.text) {
      text = r.data.text;
    }
  } catch (ex) {
    console.error('Tesseract.recognize', ex)
  }
  return text;
}
async function getTextFromArrayBuffer(arrayBuffer, type, name) {
  var resultText = "File: " + name + "\n";
  console.debug('handleFileInputChange for', resultText, type)
  switch (type) {
    case 'application/pdf':
      try {
        const pdfText = await extractPDFContent(arrayBuffer);
        resultText += pdfText;
      } catch (error) {
        resultText += "Error processing PDF content: " + error;
      }
      break;
    case 'image/png':
    case 'image/jpeg':
    case 'image/tiff':
    case 'image/x-jp2':
    case 'image/gif':
    case 'image/webp':
    case 'image/bmp':
    case 'image/x-portable-anymap':
      const imageContent = await extractImageContent(arrayBuffer);
      resultText += name + ":\n" + imageContent;
      break;
    case 'text/plain':
    case 'text/markdown':
      const textContent = await extractTextContent(arrayBuffer);
      resultText += name + ":\n" + textContent;
      break;
    default:
      if (isSupportedFileFormat(name)) {
        const textContent = await extractTextContent(arrayBuffer);
        resultText += name + ":\n" + textContent;
      } else {
        resultText += "Invalid file format for " + name;
      }
  }
  return resultText;
}
const fileFormats = '.pdf, .md, .txt, .js, .cs, .java, .py, json, .yaml, .php, .csv, .xsql, .json, .xml, png, .jpg, .jpeg, .tiff, .jp2, .gif, .webp, .bmp, .pnm';
async function handleFileInputChange(fileInput) {
  const files = fileInput.files;
  const fileCount = files.length;

  let resultText = "Importing:" + fileCount + " files...\n";
  console.debug('handleFileInputChange start', resultText)
  for (let i = 0; i < fileCount; i++) {
    const file = files[i];
    try {
      const arrayBuffer = await readFile(file);
      var rt = await getTextFromArrayBuffer(arrayBuffer, file.type, file.name)
      resultText += rt;
    } catch (error) {
      resultText += file.name + ": " + error;

    }
  }


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
  const supportedFormats = ['.md', '.txt', '.js', '.cs', '.java', '.py', '.json', '.yaml', '.php', '.sql', '.xsql', '.xml', '.csv', '.json'];
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

export default { extractFileContent, extractImageContent };