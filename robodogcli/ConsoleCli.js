const { FileService } = require( '../dist/robodog.bundle');
const fs = require('fs');
fs.readFile('../../../screenshot-ocr.jsp', (err, data) => {
    if (err) throw err;

    let arrayBuffer = Uint8Array.from(data).buffer;

    FileService.extractTextContent(arrayBuffer).then((result) => {
        console.log(result);
    });
});