import RobodogLib from '../../robodoglib/dist/robodoglib.bundle.js';


const fileService = new RobodogLib.FileService();

class ConsoleCli {

    execute(question, path) {
        console.log(question, path)
        return '';
    }
}

export { ConsoleCli };