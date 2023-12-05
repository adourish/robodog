const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const ZipPlugin = require('zip-webpack-plugin');
var currentDateTime = new Date();
const { version } = require('./package.json');
const buildNumber = Math.floor(Date.now() / 1000);
const buildInfo = currentDateTime.toDateString() + ' ' + currentDateTime.toLocaleTimeString();
module.exports = {
  entry: './src/index.tsx',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: 'robodog.bundle.js',
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
    new ZipPlugin({
      filename: 'robodog.zip',
      path: path.resolve(__dirname, 'dist')
    }),
  ],
  devServer: {
    contentBase: path.join(__dirname, 'dist'),
    compress: true,
    port: 3000,
  },
};
