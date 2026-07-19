const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const ZipPlugin = require('zip-webpack-plugin');
   const CopyWebpackPlugin = require('copy-webpack-plugin'); 
var currentDateTime = new Date();
const { version } = require('./package.json');
const buildNumber = Math.floor(Date.now() / 1000);
const buildInfo = currentDateTime.toDateString() + ' ' + currentDateTime.toLocaleTimeString();
const filename = 'robodog.bundle.js?' + currentDateTime.toDateString() + '-' + currentDateTime.toLocaleTimeString() + buildNumber;
module.exports = {
  entry: './src/index.tsx',
  mode: 'development',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: filename,
  },
  module: {
    rules: [
      {
        test: /\.(js|jsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: ['@babel/preset-env', '@babel/preset-react'],
          },
        },
      },
      {
        test: /\.tsx?$/,
        use: 'ts-loader',
        exclude: /node_modules/,
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader'],
      },
      {
        test: /\.(png|svg|jpg|jpeg|gif)$/i,
        type: 'asset/resource',
      },
    ],
  },
  resolve: {
    extensions: ['.js', '.jsx', '.ts', '.tsx'],
  },
  plugins: [
    new HtmlWebpackPlugin({
      template: './public/index.html',
      filename: 'robodog.html',
      templateParameters: {
        version,
        buildNumber,
        buildInfo
      }
    }),
    new HtmlWebpackPlugin({
      template: './public/index.html',
      filename: 'index.html',
      templateParameters: {
        version,
        buildNumber,
        buildInfo
      }
    }),
    new CopyWebpackPlugin({                                    // ← added
         patterns: [
           {
             from: path.resolve(__dirname, 'public/manifest.json'),
             to: path.resolve(__dirname, 'dist/manifest.json')
           }
         ]
       }),
    new ZipPlugin({
      filename: 'robodog.zip',
      path: path.resolve(__dirname, 'dist')
    }),
  ],
  devServer: {
    contentBase: path.join(__dirname, 'dist'),
    compress: false,
    port: 3000,
  },
};
