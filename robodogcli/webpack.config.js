const path = require('path');


module.exports = {
  entry: './src/index.js', // This is your main file
  resolve: {
    fallback: {
     "fs": false,
    "path": require.resolve("path-browserify"),
    "url": require.resolve("url/"),
    "http": require.resolve("stream-http"),
    "crypto": require.resolve("crypto-browserify"),
    "stream": require.resolve("stream-browserify"),
    "zlib": require.resolve("browserify-zlib"),
    "querystring": require.resolve("querystring-es3"),
    "assert": require.resolve("assert/"), // Add this line
    "util": require.resolve("util/"), // Add this line
    "net": require.resolve("net-browserify"), // Add this line
    "async_hooks": false // Add this line
    }
  },
  output: {
    path: path.resolve(__dirname, 'dist'), // This is where the output file will be located
    filename: 'robodogcli.bundle.js', // This is the name of your output file
    library: 'robodogcli', // This is the name of your library
    libraryTarget: 'umd', // This will make your library compatible with other environments such as AMD and Node
    umdNamedDefine: true,
    globalObject: 'this' // This is necessary to make the library work in both NodeJS and web environments
  },
  module: {
    rules: [
      {
        test: /\.js$/, 
        exclude: /(node_modules)/, // This will exclude files within the node_modules directory
        use: {
          loader: 'babel-loader', // This is your transpiler
          options: {
            presets: ['@babel/preset-env'] // This will transpile ES6+ into ES5
          }
        }
      }
    ]
  },
  mode: 'production' // This will minify the output file
};

